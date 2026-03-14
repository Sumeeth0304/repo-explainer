import asyncio
import hashlib
import os
import re
import aiohttp
from fastapi import APIRouter, HTTPException

import anthropic

from app.models.schemas import IngestRequest, IngestResponse
from app.services import vector_service

router = APIRouter()

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".cs",
    ".cpp", ".c", ".h", ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
    ".yaml", ".yml", ".json", ".toml", ".md", ".html", ".css", ".scss",
    ".sql", ".graphql", ".proto",
}
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".next", "dist", "build",
    "venv", ".venv", "vendor", ".idea", ".vscode", "coverage",
}
MAX_FILE_BYTES = 80_000
CHUNK_LINES = 60
CHUNK_OVERLAP = 10


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _language(path: str) -> str:
    mapping = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".jsx": "jsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".cs": "csharp", ".rb": "ruby", ".php": "php",
        ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".json": "json",
        ".md": "markdown", ".html": "html", ".css": "css", ".scss": "scss",
        ".sql": "sql", ".graphql": "graphql",
    }
    return mapping.get(_ext(path), "text")


def _chunk_text(text: str, file_path: str, language: str) -> list[dict]:
    lines = text.splitlines()
    chunks = []
    step = CHUNK_LINES - CHUNK_OVERLAP
    for i in range(0, len(lines), step):
        block = lines[i : i + CHUNK_LINES]
        content = "\n".join(block)
        if not content.strip():
            continue
        chunk_id = hashlib.sha256(f"{file_path}:{i}:{content[:50]}".encode()).hexdigest()[:24]
        chunks.append(
            {
                "id": chunk_id,
                "text": f"// File: {file_path}\n{content}",
                "file_path": file_path,
                "language": language,
                "start_line": i + 1,
            }
        )
    return chunks


async def _get_default_branch(session: aiohttp.ClientSession, owner: str, repo: str, headers: dict) -> str:
    async with session.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers) as r:
        if r.status == 403:
            raise HTTPException(status_code=429, detail="GitHub API rate limit exceeded. Add a GitHub Personal Access Token to increase limits.")
        if r.status == 404:
            raise HTTPException(status_code=404, detail=f"Repo {owner}/{repo} not found or is private.")
        if r.status != 200:
            raise HTTPException(status_code=502, detail=f"GitHub returned {r.status} for {owner}/{repo}")
        data = await r.json()
        return data.get("default_branch", "main")


async def _fetch_tree(session: aiohttp.ClientSession, owner: str, repo: str, branch: str, headers: dict) -> list:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    for attempt in range(3):
        try:
            async with session.get(url, headers=headers) as r:
                if r.status != 200:
                    raise HTTPException(status_code=502, detail="Failed to fetch repo tree from GitHub")
                data = await r.json(content_type=None)
                return data.get("tree", [])
        except aiohttp.ClientPayloadError:
            if attempt == 2:
                raise HTTPException(status_code=502, detail="GitHub tree response was truncated after 3 attempts")
            await asyncio.sleep(1)
    return []


async def _fetch_file(session: aiohttp.ClientSession, owner: str, repo: str, path: str, headers: dict) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    async with session.get(url, headers=headers) as r:
        if r.status != 200:
            return None
        data = await r.json()
        if data.get("encoding") == "base64":
            import base64
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None


def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    match = re.search(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
    if match:
        return match.group(1), match.group(2)
    parts = repo_url.strip("/").split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    raise HTTPException(status_code=422, detail=f"Cannot parse repo URL: {repo_url}")


async def _analyse_with_claude(repo_name: str, sample_files: list[dict]) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    file_snippets = ""
    for f in sample_files[:20]:
        snippet = f["content"][:1500]
        file_snippets += f"\n\n--- {f['path']} ---\n{snippet}"

    prompt = f"""You are a senior software engineer. Analyse this GitHub repository called "{repo_name}".

Here are key files from the repo:
{file_snippets}

Return a JSON object (no markdown fences) with exactly these keys:
- what_it_does: 2-3 sentence plain-English summary of the system's purpose
- architecture: paragraph describing the high-level architecture (frontend/backend/DB/infra)
- key_modules: array of strings, each describing a key module/package (format: "path/to/module — what it does")
- api_flows: paragraph describing the main API or data flows
- tech_stack: array of technology names detected (e.g. ["React", "FastAPI", "PostgreSQL"])
- interesting_patterns: one paragraph noting any interesting design patterns, conventions, or notable decisions

Respond with only the JSON object."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    text = message.content[0].text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "what_it_does": text[:500],
            "architecture": "",
            "key_modules": [],
            "api_flows": "",
            "tech_stack": [],
            "interesting_patterns": "",
        }


@router.post("/repos/ingest", response_model=IngestResponse)
async def ingest_repo(request: IngestRequest):
    owner, repo_name = _parse_repo_url(request.repo_url)
    repo_id = hashlib.sha256(f"{owner}/{repo_name}".encode()).hexdigest()[:16]

    gh_token = request.github_token or os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    timeout = aiohttp.ClientTimeout(total=60, sock_read=30)
    connector = aiohttp.TCPConnector(force_close=True)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        branch = await _get_default_branch(session, owner, repo_name, headers)
        tree = await _fetch_tree(session, owner, repo_name, branch, headers)

        blobs = [
            item for item in tree
            if item["type"] == "blob"
            and _ext(item["path"]) in CODE_EXTENSIONS
            and not any(skip in item["path"].split("/") for skip in SKIP_DIRS)
            and item.get("size", 0) < MAX_FILE_BYTES
        ]

        all_chunks = []
        sample_files = []

        # Fetch files concurrently in batches of 20
        async def fetch_and_chunk(item):
            content = await _fetch_file(session, owner, repo_name, item["path"], headers)
            if content is None:
                return None
            lang = _language(item["path"])
            return item["path"], content, _chunk_text(content, item["path"], lang)

        BATCH = 20
        results = []
        for i in range(0, len(blobs), BATCH):
            batch = blobs[i : i + BATCH]
            batch_results = await asyncio.gather(*[fetch_and_chunk(item) for item in batch])
            results.extend([r for r in batch_results if r])

        for path, content, chunks in results:
            all_chunks.extend(chunks)
            is_important = any(
                kw in path.lower()
                for kw in ["main", "app", "index", "router", "api", "readme", "config", "schema"]
            )
            if is_important or len(sample_files) < 10:
                sample_files.append({"path": path, "content": content})

    if not all_chunks:
        raise HTTPException(status_code=422, detail="No supported source files found in repo")

    vector_service.upsert_chunks(repo_id, all_chunks)

    analysis = await _analyse_with_claude(repo_name, sample_files)

    return IngestResponse(
        repo_id=repo_id,
        repo_name=f"{owner}/{repo_name}",
        files_processed=len(blobs),
        chunks_stored=len(all_chunks),
        status="ready",
        what_it_does=analysis.get("what_it_does"),
        architecture=analysis.get("architecture"),
        key_modules=analysis.get("key_modules"),
        api_flows=analysis.get("api_flows"),
        tech_stack=analysis.get("tech_stack"),
        interesting_patterns=analysis.get("interesting_patterns"),
    )


@router.post("/repos/check")
async def check_repo(request: IngestRequest):
    """Check if a repo is already ingested without re-ingesting it."""
    owner, repo_name = _parse_repo_url(request.repo_url)
    repo_id = hashlib.sha256(f"{owner}/{repo_name}".encode()).hexdigest()[:16]

    count = vector_service.count_chunks(repo_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="Repo not yet ingested")

    return IngestResponse(
        repo_id=repo_id,
        repo_name=f"{owner}/{repo_name}",
        files_processed=0,
        chunks_stored=count,
        status="ready",
        what_it_does="Previously ingested — data loaded from Pinecone.",
    )


@router.delete("/repos/{repo_id}")
async def delete_repo(repo_id: str):
    vector_service.delete_repo(repo_id)
    return {"status": "deleted", "repo_id": repo_id}

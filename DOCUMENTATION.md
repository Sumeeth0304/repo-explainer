# RepoMind — Project Documentation

## What is RepoMind?

RepoMind is an AI-powered tool that lets you drop in any GitHub repository URL and instantly get:

- A plain-English explanation of what the system does
- An architecture overview
- A breakdown of key modules
- The main API/data flows
- The detected tech stack
- Notable design patterns

After ingestion, you can chat with the codebase — ask questions like *"How does authentication work?"* or *"Where is the payment logic?"* and get answers grounded in the actual source code.

It is essentially a lightweight version of GitHub Copilot Workspace / Sourcegraph Cody, built from scratch.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Browser                          │
│              React + TypeScript (Vite)              │
│                 localhost:5173                       │
└────────────────────┬────────────────────────────────┘
                     │ HTTP / streaming
┌────────────────────▼────────────────────────────────┐
│               FastAPI Backend                       │
│              Python 3.14 / Uvicorn                  │
│                 localhost:8000                       │
│                                                     │
│  POST /api/repos/ingest   →  repos.py router        │
│  POST /api/repos/check    →  repos.py router        │
│  POST /api/chat           →  chat.py router         │
│  POST /api/chat/sources   →  chat.py router         │
│  DELETE /api/repos/{id}   →  repos.py router        │
└──────┬──────────────────────────┬───────────────────┘
       │                          │
┌──────▼──────┐          ┌────────▼────────┐
│   OpenAI    │          │    Pinecone     │
│ Embeddings  │          │   Vector DB     │
│  API        │          │  (Serverless)   │
└─────────────┘          └────────┬────────┘
                                  │ similarity search
                         ┌────────▼────────┐
                         │    Anthropic    │
                         │  Claude Sonnet  │
                         │  (analysis +    │
                         │   chat)         │
                         └─────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, CSS Modules |
| Backend | Python 3.14, FastAPI, Uvicorn |
| Embeddings | OpenAI `text-embedding-3-small` (1024 dimensions) |
| Vector DB | Pinecone (Serverless, cosine metric, 1024 dims) |
| AI reasoning | Anthropic Claude Sonnet (`claude-sonnet-4-6`) |
| GitHub access | GitHub REST API v3 via `aiohttp` |

---

## Project Structure

```
repo-explainer/
├── .gitignore
├── DOCUMENTATION.md
├── backend/
│   ├── .env                        # API keys (never commit this)
│   ├── .env.example                # Template with placeholder values
│   ├── requirements.txt            # Python dependencies
│   └── app/
│       ├── main.py                 # FastAPI app, CORS, explicit .env loading, startup checks
│       ├── models/
│       │   └── schemas.py          # Pydantic request/response models
│       ├── routers/
│       │   ├── repos.py            # Ingestion, check, and delete endpoints
│       │   └── chat.py             # Chat + sources endpoints
│       └── services/
│           └── vector_service.py   # Pinecone + OpenAI embeddings
└── frontend/
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts              # Proxies /api → localhost:8000
    └── src/
        ├── main.tsx
        ├── App.tsx                 # Root — switches between input and chat views
        ├── App.module.css
        ├── index.css               # Global CSS variables (dark GitHub theme)
        ├── types.ts                # Shared TypeScript interfaces
        ├── api.ts                  # fetch wrappers + streaming generator + checkRepo
        └── components/
            ├── RepoInput.tsx       # Landing page / URL form
            ├── RepoInput.module.css
            ├── OverviewPanel.tsx   # Left sidebar with AI analysis
            ├── OverviewPanel.module.css
            ├── Chat.tsx            # Chat UI with streaming + sources drawer
            └── Chat.module.css
```

---

## How Each Part Works

### 1. Check (`POST /api/repos/check`)

Before ingesting, the frontend calls this endpoint first. It computes the deterministic `repo_id` from the URL and queries Pinecone to see if vectors already exist. If they do, the full ingest is skipped and the user goes straight to chat. This prevents re-ingesting the same repo and wasting GitHub API quota.

### 2. Ingestion (`POST /api/repos/ingest`)

When a user submits a repo URL that hasn't been ingested yet, the backend:

1. **Parses the URL** — accepts `https://github.com/owner/repo` or `owner/repo` shorthand
2. **Generates a stable `repo_id`** — SHA-256 hash of `owner/repo`, truncated to 16 chars
3. **Fetches the file tree** — uses GitHub's recursive tree API to get all file paths in one call, with 3 retries on network errors
4. **Filters files** — keeps only recognised code extensions (`.py`, `.ts`, `.go`, `.rs`, etc.), skips `node_modules`, `dist`, `.git`, and files over 80KB
5. **Downloads files concurrently** — fetches 20 files at a time in parallel via `asyncio.gather`, reducing download time significantly vs sequential fetching
6. **Chunks the code** — splits each file into 60-line windows with 10-line overlap so context isn't lost at boundaries. Each chunk is prefixed with `// File: path/to/file` so the AI always knows where it came from
7. **Embeds the chunks** — sends batches of 100 chunks to OpenAI `text-embedding-3-small` with `dimensions=1024` to match the Pinecone index
8. **Upserts into Pinecone** — stores vectors with metadata (repo_id, file_path, language, start_line, text snippet)
9. **Analyses with Claude** — builds a prioritised sample of up to 20 files sent to Claude Sonnet. Files are ranked: README first, then entry points (`main`, `app`, `index`, `server`), then routers/services/models, then general files, and config/JSON files last. This ensures Claude reads the files that explain the product's *purpose* before anything else. The prompt explicitly instructs Claude to focus on what the software does and why it exists — not just the tech stack. Returns a structured JSON response: what it does, architecture, key modules, API flows, tech stack, interesting patterns.
10. **Returns the full overview** to the frontend

### 3. Chat (`POST /api/chat`)

When a user asks a question:

1. The question is embedded using the same OpenAI model (1024 dims)
2. Pinecone is queried for the **top 8 most similar code chunks** filtered by `repo_id`
3. Those chunks are assembled into a context block and sent to Claude Sonnet along with the question
4. Claude's response is **streamed** back token-by-token via `StreamingResponse`
5. The frontend appends each token to the message in real time (typewriter effect)

A companion endpoint `POST /api/chat/sources` runs the same vector search and returns the raw chunks — displayed in a collapsible drawer under each answer so users can see exactly what code the AI read.

### 4. Frontend

The UI has two states:

- **Landing page** (`RepoInput`) — URL input, optional GitHub token field, example repo buttons, animated progress bar during ingestion. On submit it calls `/check` first and skips ingestion if the repo is already stored.
- **Main view** — split layout with:
  - **Overview sidebar** (`OverviewPanel`) — repo stats, tech stack tags, architecture, key modules, API flows, reset button
  - **Chat panel** (`Chat`) — full-height chat with suggested questions on first load, streaming markdown responses with syntax-highlighted code blocks, and a "N sources retrieved" drawer per answer

All API calls are proxied through Vite (`/api → localhost:8000`) so no CORS issues in development.

---

## Key Design Decisions

### Why RAG instead of just sending all the code to Claude?
Large repos can have thousands of files and millions of tokens — far beyond any context window. RAG (Retrieval-Augmented Generation) solves this: only the 8 most relevant chunks are sent per question, keeping latency and cost low while still grounding answers in real code.

### Why chunk at 60 lines with 10-line overlap?
- 60 lines fits comfortably within embedding model token limits
- The 10-line overlap ensures a function or class split across a boundary still appears complete in at least one chunk

### Why OpenAI for embeddings and Anthropic for reasoning?
Anthropic does not offer an embeddings API — Claude is a reasoning/generation model only. OpenAI's `text-embedding-3-small` is fast and cheap (fractions of a cent per repo). Claude Sonnet handles the complex reasoning tasks.

### Why 1024 embedding dimensions instead of 1536?
OpenAI's `text-embedding-3-small` supports dimension reduction via the `dimensions` parameter. Pinecone's dashboard only offers preset options (2048, 1024, 768, 512, 384) — 1024 was chosen as the best balance between accuracy and storage cost. Quality loss vs 1536 is minimal.

### Why concurrent file fetching (batches of 20)?
Sequential fetching of hundreds of files from GitHub was taking 30+ seconds for medium repos. Fetching 20 files simultaneously reduces this to a few seconds with no risk of hitting GitHub's secondary rate limits.

### Why Pinecone Serverless?
No always-on costs — you only pay per query. For a dev tool with sporadic usage this is significantly cheaper than provisioned capacity.

### Why streaming for chat responses?
Code explanations can be long. Streaming means the user sees the first words within ~1 second instead of waiting 10–30 seconds for the full response.

### Why load `.env` with an absolute path in `main.py`?
When Uvicorn spawns worker processes (especially with `--reload`), the working directory of child processes can differ from where the server was launched. Using `os.path.abspath(__file__)` to resolve the `.env` path ensures it always loads correctly regardless of how or where the server is started.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | For Claude Sonnet (analysis + chat) |
| `OPENAI_API_KEY` | Yes | For `text-embedding-3-small` embeddings |
| `PINECONE_API_KEY` | Yes | For vector storage and search |
| `PINECONE_INDEX_NAME` | Yes | Name of the Pinecone index (default: `repo-explainer`) |
| `GITHUB_TOKEN` | No | Raises GitHub rate limit from 60 to 5,000 req/hour. Required for private repos. |
| `FRONTEND_URL` | No | Comma-separated extra origins for CORS (all `*.vercel.app` domains are allowed automatically via regex) |
| `VITE_API_URL` | No (frontend) | Full backend API URL for production (e.g. `https://xxx.up.railway.app/api`). Falls back to `/api` proxy for local dev. |

### Pinecone Index Settings
When creating the index:
- **Dimensions:** 1024
- **Metric:** Cosine
- **Type:** Serverless

---

## Deployment

### Backend — Railway
1. Create a new project on [railway.app](https://railway.app) from the GitHub repo
2. Set **Root Directory** to `backend` in service Settings
3. Add the following environment variables in Railway:
   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`
   - `PINECONE_API_KEY`
   - `PINECONE_INDEX_NAME` = `repo-explainer`
   - `GITHUB_TOKEN` (recommended — raises rate limit from 60 to 5000 req/hr)
   - `FRONTEND_URL` (optional — comma-separated list of allowed origins beyond `*.vercel.app`)
4. Generate a public domain under Settings → Networking
5. Railway uses `railway.json` to auto-configure the start command with the dynamic `$PORT`

### Frontend — Vercel
1. Import the repo on [vercel.com](https://vercel.com), set **Root Directory** to `frontend`
2. Add environment variable:
   - `VITE_API_URL` = `https://your-railway-url.up.railway.app/api` (must include `/api`, no trailing slash)
3. Deploy — all `*.vercel.app` preview and production URLs are automatically allowed by the backend CORS config

---

## Running Locally

### Backend
```bash
cd backend
pip install -r requirements.txt
python -u -m uvicorn app.main:app --reload
# Runs on http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

> For local dev, `VITE_API_URL` does not need to be set — Vite proxies `/api` to `localhost:8000` automatically.

---

## Known Limitations & Future Ideas

| Limitation | Possible Fix |
|---|---|
| GitHub rate limit (60 req/hr unauthenticated, 5000 with token) | Prompt users to add a token; cache fetched files locally |
| No persistent repo metadata — overview lost on restart | Store `repo_id → metadata` in SQLite or Redis |
| Check endpoint returns minimal overview (no AI analysis) for cached repos | Store analysis results alongside vectors in a sidecar DB |
| Large repos (1000+ files) take 1–2 min to ingest | Add a WebSocket progress stream |
| No authentication / multi-user support | Add user sessions; isolate repos in Pinecone by namespace |
| Pinecone metadata text capped at 2000 chars | Store full chunk text in a sidecar DB (SQLite) |
| Only GitHub repos supported | Support GitLab, Bitbucket, or direct zip upload |

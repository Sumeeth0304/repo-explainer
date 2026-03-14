import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import anthropic

from app.models.schemas import ChatRequest, CodeChunk
from app.services import vector_service

router = APIRouter()


def _build_system_prompt() -> str:
    return (
        "You are RepoMind, an expert code analyst. "
        "You are given relevant code snippets retrieved from a GitHub repository. "
        "Answer the user's question accurately and concisely, referencing specific files and line numbers where helpful. "
        "If the answer cannot be determined from the provided snippets, say so honestly. "
        "Format code references as `file_path:line_number`."
    )


def _build_user_message(question: str, chunks: list[dict]) -> str:
    context = ""
    for i, chunk in enumerate(chunks, 1):
        context += (
            f"\n\n--- Snippet {i} | {chunk['file_path']} (score: {chunk['score']:.2f}) ---\n"
            f"```{chunk['language']}\n{chunk['content']}\n```"
        )

    return f"""Here are the most relevant code snippets from the repository:
{context}

User question: {question}"""


@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        chunks = vector_service.query_chunks(request.repo_id, request.question)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant code found for this repo. Has it been ingested?")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_build_system_prompt(),
            messages=[
                {"role": "user", "content": _build_user_message(request.question, chunks)}
            ],
        ) as stream:
            for text in stream.text_stream:
                yield text

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/chat/sources")
async def chat_sources(request: ChatRequest):
    """Return the source chunks that would be used to answer a question."""
    try:
        chunks = vector_service.query_chunks(request.repo_id, request.question)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "sources": [
            CodeChunk(
                file_path=c["file_path"],
                content=c["content"],
                language=c["language"],
                score=c["score"],
            )
            for c in chunks
        ]
    }

import os
from typing import List, Dict, Any
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

_client: OpenAI = None
_index = None

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1024


def init_pinecone():
    global _index
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.getenv("PINECONE_INDEX_NAME", "repo-explainer")

    existing = [i.name for i in pc.list_indexes()]
    if index_name not in existing:
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    _index = pc.Index(index_name)


def _get_openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    client = _get_openai()
    # Batch in groups of 100 to stay within OpenAI limits
    embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch, dimensions=EMBEDDING_DIM)
        embeddings.extend([r.embedding for r in resp.data])
    return embeddings


def upsert_chunks(repo_id: str, chunks: List[Dict[str, Any]]):
    """
    chunks: list of dicts with keys: id, text, file_path, language, start_line
    """
    if _index is None:
        raise RuntimeError("Pinecone not initialised — call init_pinecone() first")

    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts)

    pinecone_vectors = []
    for chunk, vec in zip(chunks, vectors):
        pinecone_vectors.append(
            {
                "id": chunk["id"],
                "values": vec,
                "metadata": {
                    "repo_id": repo_id,
                    "file_path": chunk["file_path"],
                    "language": chunk["language"],
                    "start_line": chunk.get("start_line", 0),
                    "text": chunk["text"][:2000],  # Pinecone metadata cap
                },
            }
        )

    # Upsert in batches of 100
    for i in range(0, len(pinecone_vectors), 100):
        _index.upsert(vectors=pinecone_vectors[i : i + 100])


def query_chunks(repo_id: str, question: str, top_k: int = 8) -> List[Dict[str, Any]]:
    if _index is None:
        raise RuntimeError("Pinecone not initialised — call init_pinecone() first")

    [query_vec] = embed_texts([question])
    results = _index.query(
        vector=query_vec,
        top_k=top_k,
        filter={"repo_id": {"$eq": repo_id}},
        include_metadata=True,
    )

    return [
        {
            "file_path": m.metadata["file_path"],
            "content": m.metadata["text"],
            "language": m.metadata.get("language", ""),
            "score": m.score,
        }
        for m in results.matches
    ]


def count_chunks(repo_id: str) -> int:
    """Return the number of vectors stored for a repo."""
    if _index is None:
        return 0
    [vec] = embed_texts(["code"])
    result = _index.query(
        vector=vec,
        top_k=1,
        filter={"repo_id": {"$eq": repo_id}},
        include_metadata=False,
    )
    return len(result.matches)


def delete_repo(repo_id: str):
    """Remove all vectors for a repo from the index."""
    if _index is None:
        return
    # Pinecone delete by metadata filter
    _index.delete(filter={"repo_id": {"$eq": repo_id}})

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from app.routers import repos, chat
from app.services import vector_service

app = FastAPI(title="RepoMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.on_event("startup")
async def startup():
    missing = [v for v in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PINECONE_API_KEY"] if not os.getenv(v)]
    if missing:
        print(f"WARNING: Missing environment variables: {', '.join(missing)}")
    else:
        vector_service.init_pinecone()
        print("RepoMind API ready.")


@app.get("/health")
async def health():
    return {"status": "ok"}

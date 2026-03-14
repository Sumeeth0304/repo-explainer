from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from app.routers import repos, chat
from app.services import vector_service

app = FastAPI(title="RepoMind API", version="1.0.0")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
]

# Support comma-separated list of frontend URLs in env var
frontend_urls = os.getenv("FRONTEND_URL", "")
ALLOWED_ORIGINS += [u.strip() for u in frontend_urls.split(",") if u.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
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

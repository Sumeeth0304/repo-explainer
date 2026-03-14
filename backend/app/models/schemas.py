from pydantic import BaseModel
from typing import Optional, List


class IngestRequest(BaseModel):
    repo_url: str
    github_token: Optional[str] = None


class IngestResponse(BaseModel):
    repo_id: str
    repo_name: str
    description: Optional[str] = None
    files_processed: int
    chunks_stored: int
    status: str
    what_it_does: Optional[str] = None
    architecture: Optional[str] = None
    key_modules: Optional[List[str]] = None
    api_flows: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    interesting_patterns: Optional[str] = None


class ChatRequest(BaseModel):
    repo_id: str
    question: str


class CodeChunk(BaseModel):
    file_path: str
    content: str
    language: str
    score: float

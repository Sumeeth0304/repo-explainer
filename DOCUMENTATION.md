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
| Embeddings | OpenAI `text-embedding-3-small` (1536 dimensions) |
| Vector DB | Pinecone (Serverless, cosine metric) |
| AI reasoning | Anthropic Claude Sonnet (`claude-sonnet-4-6`) |
| GitHub access | GitHub REST API v3 via `aiohttp` |

---

## Project Structure

```
repo-explainer/
├── backend/
│   ├── .env                        # API keys (never commit this)
│   ├── .env.example                # Template with placeholder values
│   ├── requirements.txt            # Python dependencies
│   └── app/
│       ├── main.py                 # FastAPI app, CORS, startup checks
│       ├── models/
│       │   └── schemas.py          # Pydantic request/response models
│       ├── routers/
│       │   ├── repos.py            # Ingestion endpoint
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
        ├── api.ts                  # fetch wrappers + streaming generator
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

### 1. Ingestion (`POST /api/repos/ingest`)

When a user submits a repo URL, the backend:

1. **Parses the URL** — accepts `https://github.com/owner/repo` or `owner/repo` shorthand
2. **Generates a stable `repo_id`** — SHA-256 hash of `owner/repo`, truncated to 16 chars
3. **Fetches the file tree** — uses GitHub's recursive tree API to get all file paths in one call
4. **Filters files** — keeps only recognised code extensions (`.py`, `.ts`, `.go`, `.rs`, etc.), skips `node_modules`, `dist`, `.git`, and files over 80KB
5. **Downloads each file** — via the GitHub Contents API (base64-decoded)
6. **Chunks the code** — splits each file into 60-line windows with 10-line overlap so context isn't lost at boundaries. Each chunk is prefixed with `// File: path/to/file` so the AI always knows where it came from
7. **Embeds the chunks** — sends batches of 100 chunks to OpenAI `text-embedding-3-small`, returns 1536-dimensional vectors
8. **Upserts into Pinecone** — stores vectors with metadata (repo_id, file_path, language, start_line, text snippet)
9. **Analyses with Claude** — sends up to 20 prioritised sample files (entry points, configs, routers) to Claude Sonnet and asks for a structured JSON response covering: what it does, architecture, key modules, API flows, tech stack, interesting patterns
10. **Returns the full overview** to the frontend

### 2. Chat (`POST /api/chat`)

When a user asks a question:

1. The question is embedded using the same OpenAI model
2. Pinecone is queried for the **top 8 most similar code chunks** filtered by `repo_id`
3. Those chunks are assembled into a context block and sent to Claude Sonnet along with the question
4. Claude's response is **streamed** back token-by-token via `StreamingResponse`
5. The frontend appends each token to the message in real time (typewriter effect)

A companion endpoint `POST /api/chat/sources` runs the same vector search and returns the raw chunks — displayed in a collapsible drawer under each answer so users can see exactly what code the AI read.

### 3. Frontend

The UI has three states:

- **Landing page** (`RepoInput`) — URL input, optional GitHub token field, example repo buttons, animated progress bar during ingestion
- **Overview sidebar** (`OverviewPanel`) — always visible after ingestion; shows repo stats, tech stack tags, architecture, key modules, API flows
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

### Why Pinecone Serverless?
No always-on costs — you only pay per query. For a dev tool with sporadic usage this is significantly cheaper than provisioned capacity.

### Why streaming for chat responses?
Code explanations can be long. Streaming means the user sees the first words within ~1 second instead of waiting 10–30 seconds for the full response.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | For Claude Sonnet (analysis + chat) |
| `OPENAI_API_KEY` | Yes | For `text-embedding-3-small` embeddings |
| `PINECONE_API_KEY` | Yes | For vector storage and search |
| `PINECONE_INDEX_NAME` | Yes | Name of the Pinecone index (default: `repo-explainer`) |
| `GITHUB_TOKEN` | No | Raises GitHub rate limit from 60 to 5000 req/hour. Required for private repos. |

### Pinecone Index Settings
When creating the index manually:
- **Dimensions:** 1536
- **Metric:** Cosine
- **Type:** Serverless

---

## Running the Project

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# Runs on http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

---

## Known Limitations & Future Ideas

| Limitation | Possible Fix |
|---|---|
| GitHub rate limit (60 req/hr unauthenticated) | Prompt users to add a token; or cache fetched repos |
| No persistent repo storage — re-ingest on restart | Store `repo_id → metadata` in SQLite or Redis |
| Large repos (1000+ files) take 1–2 min to ingest | Add a progress WebSocket; process files concurrently |
| No authentication / multi-user support | Add user sessions so each user's repos are isolated in Pinecone by namespace |
| Pinecone metadata text capped at 2000 chars | Store full chunk text in a sidecar DB (SQLite) |
| Only public GitHub repos (without token) | Support GitLab, Bitbucket, or direct zip upload |

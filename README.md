# Intelligent Document Assistant

A FastAPI backend with two REST APIs: **document ingestion** and **conversational
RAG with interview booking**.

---

## What it does, against the brief

| Requirement | Where it lives |
|---|---|
| **Document Ingestion API** | |
| Upload `.pdf` or `.txt` | `POST /api/v1/documents/ingest` — `app/api/v1/documents.py` |
| Extract text | `app/utils/pdf_extractor.py`, `app/utils/text_extractor.py` (PyMuPDF) |
| Two chunking strategies, selectable | `fixed_size` and `recursive` — `app/chunking/` |
| Generate embeddings and store them in a vector DB | `all-MiniLM-L6-v2` → **Qdrant** — `app/integrations/qdrant.py` |
| Save metadata in a SQL DB | **PostgreSQL** + SQLAlchemy + Alembic — `app/models/`, `app/repositories/` |
| **Conversational RAG API** | |
| Custom RAG, no `RetrievalQAChain` | `app/services/rag_service.py` — rewrite → embed → retrieve → prompt → answer |
| Redis for chat memory | `app/services/conversation_service.py` |
| Multi-turn queries | conversation history in the prompt, plus a query rewrite — `app/services/query_rewriter.py` |
| Interview booking (name, email, date, time) using an LLM | `app/services/booking_service.py` — one structured LLM call, validated against a Pydantic schema |
| Store booking info | the `bookings` table in PostgreSQL |
| **Constraints** | |
| No FAISS, no Chroma | the vectors live in Qdrant |
| No UI | REST only |
| No `RetrievalQAChain` | the pipeline is written out stage by stage |
| Clean modular code, typed | `api → services → repositories/integrations`; `mypy --strict` is clean |

---

## Setup

You need **Docker 24+** with the Compose plugin, and about **5 GB of disk**
(the image is mostly CPU `torch`). Python, PostgreSQL and Redis are not needed
— they all run in containers.

```bash
git clone https://github.com/Sahahahil/Intelligent-Document-Assistant.git
cd Intelligent-Document-Assistant
cp .env.example .env
```

### Pick an LLM — a cloud model with a key, or a local model

**Option A — a cloud model (OpenAI, Groq, Gemini, any OpenAI-compatible endpoint):**

```bash
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=                       # empty for OpenAI
# LLM_BASE_URL=https://api.groq.com/openai/v1        # Groq
# LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/   # Gemini
```

**Option B — a local model (no key, nothing leaves the machine):**

```bash
# Ollama already running on your machine
LLM_API_KEY=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=phi3:3.8b

# ...or Ollama in the Compose stack
docker compose --profile local-llm up -d ollama
docker compose exec ollama ollama pull llama3.1:8b
# then in .env:  LLM_BASE_URL=http://ollama:11434/v1
```

Any OpenAI-compatible server works the same way — llama.cpp's `llama-server`,
LM Studio, vLLM. Only `LLM_BASE_URL` changes.

Nothing else in `.env` needs editing: the Compose file points the app at its
own containers.

---

## Run it

```bash
docker compose up --build
```

The first build takes a few minutes (it downloads CPU `torch`); after that it
reuses the layer. The API waits for PostgreSQL and Redis, applies the Alembic
migrations, and then serves on <http://localhost:8000>.

```bash
curl localhost:8000/ready      # {"status":"ready","checks":{"postgres":"ok","redis":"ok","qdrant":"ok"}}
open localhost:8000/docs       # interactive API docs
```

In the docs page: click **Try it out**, then pick the file, then **Execute**.
The file has to be attached after *Try it out* — an empty `chunk_size` field
is sent as `0`, which means "use the default".

Only `/chat` needs an LLM — ingestion, the probes and the tests do not.

**Without Docker:** `uv sync`, then `./scripts/setup_local.sh` (starts
PostgreSQL and Redis), `uv run alembic upgrade head`, and
`uv run uvicorn app.main:app --reload`. Qdrant then runs embedded on disk.

---

## A small example

```bash
# 1. ingest a document
printf 'The quarterly review is scheduled for the fifteenth of every month.\n' > handbook.txt
curl -F file=@handbook.txt -F chunking_strategy=recursive \
     localhost:8000/api/v1/documents/ingest
# {"document_id":"…","status":"completed","chunking_strategy":"recursive","total_chunks":1,"embedding_dim":384}

# 2. ask a question
curl -X POST localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
     -d '{"session_id":"demo","message":"When is the quarterly review?"}'
# {"answer":"The quarterly performance review is on the fifteenth of every month. (handbook.txt, chunk 0)",
#  "sources":[{"filename":"handbook.txt","chunk_index":0,"score":0.72}],
#  "context_used":true}

# 3. book an interview — the assistant asks for the details, then writes the row on "yes"
curl -X POST localhost:8000/api/v1/chat -H 'Content-Type: application/json' \
     -d '{"session_id":"demo","message":"I want to schedule an interview"}'

# 4. read the bookings back
curl "localhost:8000/api/v1/bookings?email=sahil@example.com"
```

---

## The API

| Method | Path | What it does |
|--------|------|--------------|
| `POST` | `/api/v1/documents/ingest` | Upload a `.pdf` / `.txt`; `chunking_strategy` is `fixed_size` or `recursive` |
| `GET` | `/api/v1/documents` | List documents, paginated, filterable by status |
| `GET` | `/api/v1/documents/{id}` | One document with its chunk count |
| `DELETE` | `/api/v1/documents/{id}` | Remove the row and its vectors |
| `POST` | `/api/v1/chat` | One conversational turn — a question, or a booking request |
| `GET` | `/api/v1/bookings` | List bookings, paginated, filterable by email or date |
| `GET` | `/health` | Liveness — the process is up |
| `GET` | `/ready` | Readiness — pings PostgreSQL, Redis and Qdrant; `503` if any is down |

Every failure comes back in one envelope:

```json
{ "error": { "code": "validation_error", "message": "…", "details": {}, "request_id": "…" } }
```

---

## Tests

```bash
uv run pytest                    # unit tests — no network, no database
uv run pytest -m integration     # against a real PostgreSQL and Redis
./scripts/smoke.sh              # the whole stack, end to end
```

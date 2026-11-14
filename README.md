# Intelligent Document Assistant

A FastAPI backend that turns PDFs and text files into a conversational,
source-grounded RAG assistant with an LLM-driven interview booking flow.

- **Document ingestion** — upload a `.pdf` / `.txt`, extract the text, chunk it
  with a selectable strategy, embed it, store the vectors in Qdrant and the
  metadata in PostgreSQL.
- **Conversational RAG** — ask questions across your documents with multi-turn
  memory in Redis. The answer comes back with the passages it was built from.
- **Interview booking** — the same chat endpoint extracts name, email, date and
  time with an LLM and stores the booking once you confirm it.

No FAISS, no Chroma, no LangChain, no `RetrievalQAChain`, no UI.

---

## Run it

```bash
cp .env.example .env      # set LLM_API_KEY and LLM_MODEL
docker compose up --build
```

That is the whole setup: PostgreSQL, Redis, Qdrant and the API come up
together, and the Alembic migrations run on the way up.

```bash
curl http://localhost:8000/health    # {"status":"ok"}
curl http://localhost:8000/ready     # 200 + a per-dependency report
open http://localhost:8000/docs       # interactive API docs
```

The API is at <http://localhost:8000>. Only `/chat` needs an LLM key —
ingestion, the probes and the tests do not.

**Local development** (no containers): `uv sync`, then
`./scripts/setup_local.sh` for PostgreSQL and Redis, `uv run alembic upgrade
head`, and `uv run uvicorn app.main:app --reload`. Qdrant then runs embedded
on disk — same code, no server.

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

Every failure comes back in one envelope, so a client never parses two error
formats:

```json
{ "error": { "code": "validation_error", "message": "...", "details": {}, "request_id": "..." } }
```

### Try it

```bash
# ingest
curl -F file=@handbook.pdf -F chunking_strategy=recursive \
     http://localhost:8000/api/v1/documents/ingest

# ask
curl -X POST http://localhost:8000/api/v1/chat \
     -H 'Content-Type: application/json' \
     -d '{"session_id": "demo", "message": "When is the quarterly review?"}'

# book an interview - same endpoint
curl -X POST http://localhost:8000/api/v1/chat \
     -H 'Content-Type: application/json' \
     -d '{"session_id": "demo", "message": "I want to schedule an interview"}'
```

The chat response carries the answer, the sources it came from and the booking
block:

```json
{
  "session_id": "demo",
  "answer": "The quarterly performance review is scheduled for the fifteenth of every month.",
  "sources": [
    { "document_id": "…", "filename": "handbook.pdf", "chunk_index": 0, "score": 0.57 }
  ],
  "booking": null,
  "context_used": true
}
```

---

## How it works

```
                ┌──────────────┐
  upload ──────▶│  Ingestion   │──▶ chunks ──▶ embeddings ──▶ Qdrant
                └──────┬───────┘                              (semantics)
                       │ metadata
                       ▼
                  PostgreSQL                        Redis
                (documents, bookings)          (conversation memory)
```

### Ingestion

```
validate extension + size
  → SHA-256 content hash (duplicate detection)
  → extract text (PyMuPDF / plain text)
  → chunk with the selected strategy
  → embed every chunk
  → upsert vectors + payload to Qdrant
  → write document metadata to PostgreSQL
```

Two details that matter more than they look:

- **Duplicates are detected by content hash, not filename.** Re-uploading the
  same file returns `409 Conflict` instead of creating a second copy of the
  same knowledge.
- **PostgreSQL and Qdrant cannot share a transaction.** The row is written
  first with `status=processing`; if a later step fails, the row is marked
  `failed`, any partial vectors are deleted, and the request fails loudly.

### The two chunking strategies

Both return the same structure (`content`, `chunk_index`, `document_id`,
`token_count`, `strategy`, `start_char`, `end_char`), so they are
interchangeable downstream.

- **Fixed size with overlap** — tokenise, then emit windows of `chunk_size`
  tokens advancing by `chunk_size - chunk_overlap`, so consecutive chunks share
  context and a fact split across a boundary is still whole in one of them.
- **Recursive character splitting** — split on the most structural separator
  available (paragraph → line → sentence → word), recursing only when a piece
  is still too large, then re-merging up to `chunk_size` with overlap. A
  heading stays attached to its paragraph; a sentence is not cut in half.

Fixed-size is predictable and cheap; recursive produces chunks a human would
recognise as coherent units. The strategy is chosen per upload and recorded on
the document row.

### The RAG pipeline

No `RetrievalQAChain`, no LangChain — every stage is explicit:

1. **Load history** from Redis for the session.
2. **Contextualise the question.** "What about the second one?" is useless on
   its own. With history, an LLM rewrites it into a standalone question; with
   no history, no LLM call is made at all.
3. **Embed** the rewritten question with the ingestion-time model.
4. **Retrieve** the top-k chunks from Qdrant, optionally filtered to specific
   documents.
5. **Assemble the prompt** — system rules, the retrieved context, the history
   and the original question.
6. **Generate** the answer.
7. **Persist** both messages to Redis, refreshing the session TTL.

The rewritten question is used **only** for retrieval; the answer is always
generated against what the user actually asked. Two guards keep it honest: the
system prompt forbids inventing information and requires the model to say when
the documents do not contain the answer, and the retrieved context is returned
as `sources` so every claim traces back to a file and a chunk index.

### Interview booking

Booking is a different problem from asking a question, so it gets a different
path — but it is the same conversation.

```
User: I want to schedule an interview.
Bot:  Sure — may I have your name, email, date and time?
User: Sahil Duwal, sahil@example.com, November 20 2026, 2 PM.
Bot:  Here is what I have: … Please confirm to book.
User: yes
Bot:  Your interview request for 2026-11-20 at 14:00 has been recorded.
```

- **Intent detection and extraction are one LLM call** returning a
  Pydantic-validated object (`is_booking_request`, `name`, `email`, `date`,
  `time`). The model is instructed never to invent a value it was not given.
- **Partial details accumulate in Redis** under `booking_draft:{session_id}`, so
  a bare "November 20" is understood in context and a corrected value
  overwrites the old one.
- **Nothing is written to PostgreSQL until the user confirms.** "Hmm" is not a
  confirmation. This is the single rule that makes the bookings table
  trustworthy.
- **A slot belongs to one interview.** A unique index on
  `(interview_date, interview_time)` makes double-booking impossible in the
  database, whoever tries. The row *is* the booking — cancelling removes it,
  which frees the slot.
- **The assistant records a request** — it does not claim an interview with an
  employer is scheduled, because there is no calendar behind it.

---

## Design decisions

- **Custom RAG, every stage explicit.** Retrieval → prompt → answer, with the
  sources returned, so the answer can be checked rather than trusted.
- **Two chunking strategies, selectable per upload.** Fixed for predictable
  structure, recursive for prose; both are pure functions with no I/O.
- **Redis list plus TTL for chat memory.** One key per session, capped in
  length, expiring when idle — a session disappearing is the desired
  behaviour, not a bug.
- **A unique index guards the booking slot.** The database is the last line of
  defence against double-booking; the application check before it only saves
  the user a failed request.
- **The booking check runs before retrieval.** It is cheap and unambiguous, and
  a booking request should not pull document context into its reply.
- **One uniform error envelope** for every failure, with a request id, so a
  client never has to parse two error formats.
- **Liveness and readiness are separate.** `/health` touches nothing, so a
  database blip never restarts a healthy container; `/ready` pings all three
  stores and answers `503` with the failing one named.
- **The embedding model loads lazily.** `torch` is a multi-gigabyte install;
  importing it at startup would make boot slow and the test suite painful.

---

## Project structure

Layered so that each concern can be tested on its own:

```
app/
├── api/          # routers — HTTP only, no business logic
│   └── v1/       # documents.py, chat.py, bookings.py
├── core/         # settings, exception types
├── schemas/      # Pydantic request/response models
├── models/       # SQLAlchemy ORM models
├── services/     # business logic (ingestion, rag, retrieval, booking, …)
├── chunking/     # the two strategies + factory
├── repositories/ # SQL, isolated from services
├── integrations/ # Qdrant, Redis, LLM client
├── db/           # engine, session, Base
└── utils/        # PDF and text extraction

tests/{unit,integration}/
scripts/          # setup_local.sh, smoke.sh
```

The dependency direction is one-way: `api → services → repositories/integrations`.
Services never import from `api`, and the API layer never touches a database
session directly.

---

## Tests

```bash
uv run pytest                    # unit tests — no network, no database
uv run pytest -m integration     # against the local PostgreSQL and Redis
./scripts/smoke.sh              # the whole stack, end to end
```

The unit tests run against fakes — the LLM, the vector store and the session
are stubbed, so the suite is fast and needs nothing running. The integration
tests run against the real PostgreSQL and Redis. `mypy --strict` is clean, and
`ruff` is the only linter.

The smoke script is the end-to-end check: it boots Compose, waits for
`/ready`, ingests a PDF, lists it, asks a question, deletes it, reads a
stored booking back and asserts the error envelope on a blank message. It
cleans up after itself, and it passes without an LLM key (the chat turn is then
expected to answer `502` — the API is up, the upstream is not).

---

## Known limitations

- No authentication or rate limiting — the routes are structured so a
  dependency can be added in one place.
- No streaming responses, no reranking, no OCR for scanned PDFs.
- The embedding model truncates at 256 word-pieces, so the default chunk size
  is 200 words; larger chunks would silently lose their tails.
- PostgreSQL and Qdrant are not updated in a single transaction; the
  compensating delete in the ingestion service is the mitigation, not a
  guarantee.
- The booking intent check costs one extra LLM call per chat turn.

---

## Constraints honoured

- ❌ No FAISS
- ❌ No Chroma
- ❌ No `RetrievalQAChain`
- ❌ No LangChain
- ❌ No UI
- ✅ Two selectable chunking strategies, implemented from scratch
- ✅ Custom RAG pipeline, every stage explicit
- ✅ Redis-backed multi-turn conversation memory
- ✅ LLM-driven structured booking extraction with explicit user confirmation
- ✅ Clean modular code with full type annotations

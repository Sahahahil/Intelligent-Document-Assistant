# Intelligent Document Assistant

A full-stack RAG document assistant: upload your files, ask questions and get
answers cited back to the chunks they came from, then book an interview without
leaving the app.

The interface follows the design in
[`docs/Intelligent Document Assistant.html`](docs/Intelligent%20Document%20Assistant.html)
— a chat with sessions, a document library with live indexing progress, and a
four-step booking wizard.

## Features

- **Document library** — drag-and-drop PDF/TXT upload, background extraction →
  chunking → embedding → indexing, with a live progress bar per file
- **RAG chat** — streamed answers over SSE, with the source chunks shown under
  the answer; conversation history per session in Redis
- **Interview booking** — a wizard (date → time → details → confirm) that
  refuses slots already taken, plus a list of upcoming interviews
- **Booking through chat** — the assistant recognises a booking request,
  collects the details and only writes a row after the user confirms
- **Light and dark themes**, responsive down to a phone

## Why these tools

The brief left a few choices open; each one was picked against a requirement.

| Area | Choice | Why |
|---|---|---|
| Vector store | **Qdrant** | One container, and it also runs embedded in-process, so the tests need no server. Pinecone needs an account and a key; Weaviate and Milvus bring a topology to learn before anything runs. |
| Metadata | **PostgreSQL** + SQLAlchemy + Alembic | The rule that matters — one interview per slot — is a unique index, so the database enforces it instead of the application. Alembic keeps the schema history reviewable. |
| Chat memory | **Redis** | Cross-turn state that survives a restart, is shared between workers, and expires on its own TTL. A per-process dict loses the conversation on redeploy. |
| RAG | **Hand-written** | History → rewrite → embed → retrieve → prompt → answer, one module per stage. Retrieval misses and chunk scores stay visible instead of hidden inside a chain. |
| Embeddings | **Sentence Transformers** `all-MiniLM-L6-v2` | 384-dim, CPU-only, no API key: ingestion runs offline and cannot fail because the LLM provider is down. |
| API | **FastAPI** + Pydantic v2 | One model is the schema, the validator and the OpenAPI definition; `Annotated` dependencies are typed injection without a DI container. |
| PDF text | **PyMuPDF** | Fast and dependency-light, and its block structure keeps paragraphs intact for the recursive chunker. |
| LLM | **OpenAI SDK**, any compatible `base_url` | One client for OpenAI, Groq, Gemini, Ollama and vLLM — `.env` changes, not code. |
| Tests | **pytest** + httpx `ASGITransport` | The real app in-process against real PostgreSQL, Redis and Qdrant; no mock of the framework itself. |

## Tech Stack

### Backend (apps/api)

- **FastAPI** + Pydantic v2, `httpx`/`openai` for any OpenAI-compatible LLM
- **PostgreSQL** (async SQLAlchemy) for documents and bookings
- **Redis** for conversation memory and booking drafts
- **Qdrant** for the vectors (embedded on disk by default, or a server)
- **Alembic** for migrations, **sentence-transformers** for embeddings

### Frontend (apps/web)

- **Next.js 16** App Router, React 19, TypeScript
- **Tailwind CSS 4** with the palette from the design as CSS variables
- **TanStack Query** for server state
- **NextAuth.js**, **shadcn/ui**, **lucide-react**

### Shared (packages/shared)

- **Zod schemas** mirroring the Pydantic models — one contract for both sides
- **API client** with SSE streaming, used by the app and covered by unit tests

### Infrastructure

- **Nx monorepo** (npm workspaces), **Docker Compose**, **GitHub Actions**,
  **Playwright** for E2E

## Quick Start

### With Docker (everything in one command)

```bash
cp .env.example .env          # then set LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
docker compose up -d --build
```

Then open **http://localhost:3000**. The API is on http://localhost:8000
(Swagger UI at `/docs`).

The compose file starts PostgreSQL, Redis, Qdrant, the API and the web app.
The browser only ever talks to one origin: the web app proxies `/api/v1/*` to
the API, so there is no CORS to configure.

### Without Docker

```bash
npm install                     # installs every workspace
docker compose up -d postgres redis qdrant   # just the data stores

cd apps/api && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --reload

cd apps/web && npm run dev     # http://localhost:3000
```

## Environment Variables

Copy `.env.example` to `.env`. Docker Compose overrides the database, Redis and
Qdrant addresses with its own, so locally you only need the LLM:

```bash
# LLM - any OpenAI-compatible endpoint (OpenAI, Groq, Gemini, Ollama, vLLM)
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Auth (shared with NextAuth.js)
NEXTAUTH_SECRET=$(openssl rand -base64 32)
NEXTAUTH_URL=http://localhost:3000
```

The rest (`DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `CHUNK_SIZE`,
`TOP_K`, `MAX_UPLOAD_MB`, …) have working defaults — see
[`.env.example`](.env.example).

## Project Structure

```
Intelligent_Document_Assistant/
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/v1/         # routes: chat, documents, bookings, auth
│   │   │   ├── core/           # settings, error envelope
│   │   │   ├── db/             # session and base
│   │   │   ├── integrations/   # qdrant, redis, llm clients
│   │   │   ├── models/         # SQLAlchemy models
│   │   │   ├── repositories/   # data access
│   │   │   ├── schemas/        # Pydantic request/response models
│   │   │   ├── services/       # rag, retrieval, booking, ingestion, chat
│   │   │   ├── chunking/       # recursive and fixed-size chunkers
│   │   │   └── utils/          # pdf and text extraction
│   │   └── pyproject.toml
│   │
│   ├── web/                    # Next.js frontend
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── (app)/      # chat, documents, bookings (behind the nav)
│   │   │   │   ├── api/auth/   # NextAuth route handler
│   │   │   │   ├── login/      # sign-in page
│   │   │   │   ├── global.css  # the palette from the design
│   │   │   │   └── layout.tsx  # fonts, providers, theme bootstrap
│   │   │   ├── components/     # chat, layout and ui components
│   │   │   └── lib/            # auth, query client, helpers
│   │   └── e2e/                # Playwright specs
│   │
│   └── web-e2e/                # standalone Playwright project
│
├── packages/shared/             # Zod schemas + API client
│   └── src/{schemas,client,constants}/
│
├── tests/                       # backend tests
│   ├── unit/
│   ├── integration/             # needs PostgreSQL and Redis
│   └── fakes/
│
├── alembic/                     # migrations (versions/, env.py)
├── docs/                        # the design this UI follows
├── scripts/                     # deploy, entrypoint, local setup, smoke
├── docker-compose.yml           # local development
├── docker-compose.prod.yml      # production, behind nginx
├── nginx.conf                   # TLS termination and rate limits
└── nx.json
```

## API

FastAPI serves the OpenAPI docs at http://localhost:8000/docs.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat` | One chat turn, answered in full |
| POST | `/api/v1/chat/stream` | One chat turn, streamed as SSE |
| POST | `/api/v1/documents/ingest` | Upload a document (starts indexing) |
| GET | `/api/v1/documents` | List documents (`status`, `search`, paging) |
| GET | `/api/v1/documents/{id}` | Document details |
| GET | `/api/v1/documents/{id}/status/stream` | Indexing progress (SSE) |
| DELETE | `/api/v1/documents/{id}` | Delete a document and its vectors |
| GET | `/api/v1/bookings` | List bookings (`email`, `interview_date`, paging) |
| POST | `/api/v1/bookings` | Book a slot (409 if it is taken) |
| GET | `/api/v1/bookings/{id}` | One booking |
| DELETE | `/api/v1/bookings/{id}` | Cancel a booking, freeing the slot |
| GET | `/api/v1/auth/verify` | Validate a NextAuth JWT |

The stream events are `token`, `sources`, `booking`, `error` and `done`.

### App routes

| Route | Page |
|-------|------|
| `/chat` | Chat with the session sidebar (default landing page) |
| `/documents` | Upload and watch the document library |
| `/documents/{id}` | One document's metadata |
| `/bookings` | Booking wizard and upcoming interviews |
| `/login` | Sign-in page |

## Development

Everything runs through Nx from the repository root:

```bash
npm run build         # build every project
npm test              # unit tests (Vitest + pytest)
npm run lint          # eslint + ruff
npm run typecheck     # tsc
```

Or target one project:

```bash
npx nx build web
npx nx test web
npx nx serve web      # dev server on :3000
```

Backend tests live at the repository root and use the API's pytest config:

```bash
cd apps/api
uv run pytest ../../tests/unit -v
uv run pytest ../../tests/integration -v   # needs PostgreSQL and Redis
```

Migrations:

```bash
cd apps/api
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## Deployment

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

The production stack puts nginx in front: it terminates TLS, rate-limits the
API and serves the app. Put your certificates in `./certs/` and adjust
`nginx.conf`. `NEXTAUTH_SECRET` must be set to a real secret.

The web image bakes the API address into its build, because Next.js resolves
`/api/v1/*` rewrites at build time:

```bash
docker compose build --build-arg NEXT_PUBLIC_API_URL=http://api:8000 web
```

## Known Gaps

- **No login endpoint yet.** The sign-in page posts to `/api/v1/auth/login`,
  which the API does not implement — the app runs unauthenticated and the
  navigation shows "Demo user". The API only exposes `/auth/verify`.
- **Five backend test files still fail to import** (`QueryRewriter` became a
  function, `rewrite_query`); they need updating against the current services.
- **Bookings have no interview type.** The design shows a
  Screening/Technical/Final picker, but the booking table stores only name,
  email, date and time — so the field is not in the UI.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

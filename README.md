# Intelligent Document Assistant

A full-stack RAG-powered document assistant with chat, document management, and interview booking capabilities.

## Features

- **Document Management**: Upload PDF/TXT documents, automatic chunking, embedding, and vector storage
- **RAG Chat**: Streaming conversational AI with source citations
- **Interview Booking**: Step-by-step booking wizard with calendar view
- **Document Processing**: PDF text extraction, recursive/fixed-size chunking, vector embeddings
- **Multi-session Chat**: Persistent conversation history with Redis

## Tech Stack

### Backend (apps/api)
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Primary database (async with SQLAlchemy)
- **Redis** - Conversation memory & session storage
- **Qdrant** - Vector database for embeddings
- **Alembic** - Database migrations

### Frontend (apps/web)
- **Next.js 16** - React framework with App Router
- **Tailwind CSS 4** - Utility-first styling
- **TanStack Query** - Server state management
- **NextAuth.js** - Authentication (Credentials, GitHub, Google)
- **shadcn/ui** - Accessible component library
- **react-day-picker** - Date selection
- **react-markdown** - Markdown rendering

### Shared (packages/shared)
- **Zod schemas** - Type-safe API contracts (mirroring Pydantic)
- **Type-safe API client** - SSE streaming support

### Infrastructure
- **Nx Monorepo** - Unified build system
- **Docker Compose** - Local development & production
- **GitHub Actions** - CI/CD pipeline
- **Playwright** - E2E testing

## Quick Start

### Prerequisites
- Node.js 20+
- Python 3.11+
- Docker & Docker Compose
- uv (Python package manager)

### Local Development

```bash
# Clone and enter directory
git clone <repo-url>
cd Intelligent_Document_Assistant

# Start all services
docker compose up -d

# Backend (in separate terminal)
cd apps/api
uv sync
uv run uvicorn app.main:app --reload

# Frontend (in separate terminal)
cd apps/web
npm install
npm run dev
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Auth
NEXTAUTH_SECRET=your-secret-key
NEXTAUTH_URL=http://localhost:3000

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333

# LLM (any OpenAI-compatible provider)
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## Project Structure

```
Intelligent_Document_Assistant/
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/         # API routes
│   │   │   ├── core/        # Config, exceptions
│   │   │   ├── db/          # Database models, session
│   │   │   ├── integrations/ # Qdrant, Redis, LLM
│   │   │   ├── models/      # SQLAlchemy models
│   │   │   ├── repositories/ # Data access layer
│   │   │   ├── schemas/     # Pydantic schemas
│   │   │   └── services/    # Business logic
│   │   ├── alembic/         # Migrations
│   │   └── tests/           # Unit & integration tests
│   │
│   └── web/                 # Next.js frontend
│       ├── src/
│       │   ├── app/         # App Router pages
│       │   ├── components/  # React components
│       │   ├── hooks/       # Custom hooks
│       │   ├── lib/         # Utilities, API client
│       │   └── components/ui/ # shadcn/ui components
│       ├── e2e/             # Playwright E2E tests
│       └── public/
│
├── packages/
│   └── shared/              # Shared TypeScript/Zod schemas
│       └── src/
│           ├── schemas/     # Zod schemas
│           ├── client/      # API client
│           └── constants/   # Shared constants
│
├── .github/workflows/       # GitHub Actions CI/CD
├── docs/adr/               # Architecture Decision Records
├── docker-compose.yml      # Local development
├── docker-compose.prod.yml # Production deployment
├── nx.json                 # Nx workspace config
└── package.json            # Root package.json
```

## API Documentation

FastAPI provides automatic API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat` | Non-streaming chat |
| POST | `/api/v1/chat/stream` | Streaming chat (SSE) |
| POST | `/api/v1/documents/ingest` | Upload document |
| GET | `/api/v1/documents` | List documents |
| GET | `/api/v1/documents/{id}` | Get document details |
| GET | `/api/v1/documents/{id}/status/stream` | Document processing status (SSE) |
| DELETE | `/api/v1/documents/{id}` | Delete document |
| GET | `/api/v1/bookings` | List bookings |
| POST | `/api/v1/bookings` | Create booking |
| GET | `/api/v1/auth/verify` | Verify JWT token |

## Development

### Running Tests

```bash
# Backend tests
cd apps/api
uv run pytest tests/unit -v
uv run pytest tests/integration -v

# Frontend tests
cd apps/web
npm run test          # Unit tests (Vitest)
npm run test:e2e      # E2E tests (Playwright)

# Linting
cd apps/web && npm run lint
cd apps/api && uv run ruff check .
```

### Database Migrations

```bash
cd apps/api
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## Deployment

### Production with Docker Compose

```bash
# Build and start production services
docker compose -f docker-compose.prod.yml up -d --build
```

### Environment Variables (Production)

```bash
# Required
NEXTAUTH_SECRET=generate-with-openssl-rand-base64-32
NEXTAUTH_URL=https://your-domain.com
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0
QDRANT_URL=http://host:6333
LLM_API_KEY=your-production-key
LLM_MODEL=gpt-4o-mini
```

### SSL/HTTPS

The production Docker Compose includes Nginx for SSL termination. Place certificates in `./certs/` and update `nginx.conf`.

## Architecture Decisions

See [ADRs](docs/adr/) for key architectural decisions:
- ADR 001: Nx Monorepo
- ADR 002: Next.js Frontend
- ADR 003: NextAuth.js Authentication
- ADR 004: SSE Streaming

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
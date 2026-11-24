"""The custom RAG chain: history → query → retrieval → prompt → answer.

Written out by hand — no LangChain, no `RetrievalQAChain`.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.core.config import get_settings
from app.integrations.llm import ChatMessage, LLMClient
from app.schemas.chat import SourceModel
from app.integrations.qdrant import RetrievedChunk, VectorStore
from app.services.embedding_service import EmbeddingService
from app.services.query_rewriter import rewrite_query

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a document assistant. Answer the user's question using ONLY the
supplied context.

Rules:
1. Use only the provided context to answer.
2. If the answer is not present in the context, say so explicitly
   ("The provided documents do not contain that information").
3. Do not invent facts, citations, or document names.
4. Keep answers concise and structured; use short paragraphs or bullet lists.
5. When the context is relevant, cite the source filenames inline,
   e.g. (machine_learning.pdf).
6. Stay consistent with the conversation history; treat follow-ups as
   continuing the same topic.
7. Reply with the answer only - never repeat the "Context:" or "Question:"
   labels or any other scaffolding.
"""

MAX_HISTORY_MESSAGES = 6
MAX_MESSAGE_CHARS = 2000
MAX_CONTEXT_CHARS = 8000
ANSWER_TEMPERATURE = 0.2

NO_CONTEXT = "(no relevant context was found in the document collection)"


@dataclass(frozen=True, slots=True)
class RAGAnswer:
    """The answer plus what it was grounded in."""

    answer: str
    sources: list["SourceReference"]
    rewritten_query: str
    context_used: bool


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Where an answer came from — a pointer, not the text."""

    document_id: UUID
    filename: str
    chunk_index: int
    score: float


class RAGService:
    """Answers a question from the ingested documents."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        llm: LLMClient,
    ) -> None:
        self._vector_store = vector_store
        self._embeddings = embedding_service
        self._llm = llm

    async def _retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_ids: Sequence[UUID] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """The chunks that best answer the query, closest first.

        An empty result means the documents do not cover the question — the
        caller must say so rather than answer from the model's own priors.
        """
        if not query or not query.strip():
            from app.core.exceptions import ValidationError
            raise ValidationError("Query must not be empty")

        settings = get_settings()
        limit = settings.top_k if top_k is None else top_k
        if limit < 1:
            from app.core.exceptions import ValidationError
            raise ValidationError("top_k must be at least 1")
        threshold = settings.score_threshold if score_threshold is None else score_threshold

        # An empty list means "no filter", not "match nothing".
        ids = list(document_ids) if document_ids else None

        # The same model that embedded the documents must embed the query.
        vector = await asyncio.to_thread(self._embeddings.embed_query, query)
        # Qdrant returns the points ordered by descending score.
        return await self._vector_store.search(
            vector, top_k=limit, document_ids=ids, score_threshold=threshold
        )

    async def _prepare(
        self,
        message: str,
        history: Sequence[ChatMessage],
        document_ids: Sequence[UUID] | None = None,
    ) -> tuple[str, list[RetrievedChunk], str]:
        """Common prep for answer/astream: rewrite query, retrieve chunks, build context.

        Returns (prompt, used_chunks, rewritten_query).
        """
        rewritten = await rewrite_query(self._llm, message, history)
        chunks = await self._retrieve(rewritten, document_ids=document_ids)
        context, used = self._build_context(chunks)
        prompt = self._build_prompt(message, history, context, bool(used))
        return prompt, used, rewritten

    async def answer(
        self,
        message: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[UUID] | None = None,
    ) -> RAGAnswer:
        """Answer one user message, grounded in the retrieved chunks."""
        prompt, used, rewritten = await self._prepare(message, history, document_ids)
        text = await self._llm.complete(
            messages=[
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=ANSWER_TEMPERATURE,
        )
        return RAGAnswer(
            answer=text,
            sources=[
                SourceReference(
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    score=round(chunk.score, 4),
                )
                for chunk in used
            ],
            rewritten_query=rewritten,
            context_used=bool(used),
        )

    async def astream(
        self,
        message: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[UUID] | None = None,
    ):
        """Stream one user message answer, grounded in the retrieved chunks."""
        prompt, used, rewritten = await self._prepare(message, history, document_ids)

        sources = [
            SourceModel(
                document_id=chunk.document_id,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
                score=round(chunk.score, 4),
            )
            for chunk in used
        ]

        # Stream the answer
        async for token in self._llm.astream(
            messages=[
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=ANSWER_TEMPERATURE,
        ):
            yield token

        # Yield sources at the end
        yield {"sources": sources, "rewritten_query": rewritten, "context_used": bool(used)}

    def _build_context(self, chunks: Sequence[RetrievedChunk]) -> tuple[str, list[RetrievedChunk]]:
        """The context block, capped at `MAX_CONTEXT_CHARS`.

        Returns the block and the chunks that made it into it - a chunk that
        did not fit is not a source of the answer.
        """
        parts: list[str] = []
        used: list[RetrievedChunk] = []
        total = 0
        for chunk in chunks:
            if not chunk.content.strip():
                continue
            block = (
                f"[{len(parts) + 1}] ({chunk.filename}, chunk {chunk.chunk_index})\n"
                f"{chunk.content}\n"
            )
            if total + len(block) > MAX_CONTEXT_CHARS:
                logger.warning(
                    "Context truncated at %d chars: %d of %d chunk(s) dropped",
                    MAX_CONTEXT_CHARS,
                    len(chunks) - len(used),
                    len(chunks),
                )
                break
            parts.append(block)
            used.append(chunk)
            total += len(block)
        return "\n".join(parts), used

    def _build_prompt(
        self,
        message: str,
        history: Sequence[ChatMessage],
        context: str,
        has_context: bool,
    ) -> str:
        history_block = (
            "\n".join(
                f"{item.role}: {item.content[:MAX_MESSAGE_CHARS]}"
                for item in history[-MAX_HISTORY_MESSAGES:]
            )
            or "(none)"
        )
        context_block = context if has_context else NO_CONTEXT
        return (
            f"Conversation so far:\n{history_block}\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question: {message}"
        )

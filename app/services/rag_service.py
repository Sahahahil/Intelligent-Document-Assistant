"""The custom RAG chain: history → query → retrieval → prompt → answer.

Written out by hand — no LangChain, no `RetrievalQAChain`.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.integrations.llm import ChatMessage, LLMClient
from app.integrations.qdrant import RetrievedChunk
from app.services.query_rewriter import QueryRewriter
from app.services.retrieval_service import RetrievalService, SourceReference

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
    sources: list[SourceReference]
    rewritten_query: str
    context_used: bool


class RAGService:
    """Answers a question from the ingested documents."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        llm: LLMClient,
        rewriter: QueryRewriter | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._llm = llm
        self._rewriter = rewriter

    async def answer(
        self,
        message: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[UUID] | None = None,
    ) -> RAGAnswer:
        """Answer one user message, grounded in the retrieved chunks."""
        rewritten = await self._rewrite(message, history)
        chunks = await self._retrieval.retrieve(rewritten, document_ids=document_ids)
        context, used = self._build_context(chunks)
        prompt = self._build_prompt(message, history, context, bool(used))
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

    async def _rewrite(self, message: str, history: Sequence[ChatMessage]) -> str:
        """The retrieval query - the original message unless a rewriter is wired."""
        if self._rewriter is None:
            return message
        rewritten = (await self._rewriter.rewrite(message, history)).strip()
        return rewritten or message

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

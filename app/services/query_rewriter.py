"""Turns a context-dependent follow-up into a standalone search query.

The rewritten query is used for retrieval only - the user still sees, and the
answer prompt still asks about, what they actually typed.
"""

import logging
from collections.abc import Sequence

from app.integrations.llm import ChatMessage, LLMClient

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 6
MAX_OUTPUT_CHARS = 500

REWRITE_INSTRUCTION = (
    "You rewrite a follow-up question into a standalone question that can be searched "
    "against a document collection.\n"
    "Rules:\n"
    "1. Resolve pronouns and references using the conversation.\n"
    "2. Keep the user's intent.\n"
    "3. Output ONLY the rewritten question, no quotes, no explanation.\n"
    "4. If the question is already standalone, repeat it unchanged."
)

SUMMARY_INSTRUCTION = (
    "Summarise the conversation so far in at most three sentences. "
    "Name the concrete subjects being discussed. Output only the summary."
)


class QueryRewriter:
    """Rewrites a follow-up into a query that retrieves the right chunks."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def rewrite(self, message: str, history: Sequence[ChatMessage]) -> str:
        """The standalone query for `message` - the original message on any failure."""
        if not history:
            return message
        messages = [ChatMessage(role="system", content=REWRITE_INSTRUCTION)]
        messages.extend(history[-MAX_HISTORY_MESSAGES:])
        messages.append(ChatMessage(role="user", content=message))
        try:
            rewritten = await self._llm.complete(messages=messages, temperature=0.0)
        except Exception:
            # A failed rewrite must not fail the answer - the original message
            # is a worse query, not a broken request.
            logger.warning("Query rewriting failed; using the original message", exc_info=True)
            return message
        cleaned = self._clean(rewritten)
        if not cleaned:
            logger.warning("Query rewriting produced an unusable query; using the original message")
            return message
        return cleaned

    async def summarize_conversation(self, history: Sequence[ChatMessage]) -> str:
        """A short summary of the conversation - empty on any failure."""
        if not history:
            return ""
        messages = [ChatMessage(role="system", content=SUMMARY_INSTRUCTION)]
        messages.extend(history[-MAX_HISTORY_MESSAGES:])
        try:
            summary = await self._llm.complete(messages=messages, temperature=0.0)
        except Exception:
            logger.warning("Conversation summarisation failed", exc_info=True)
            return ""
        return summary.strip()[:MAX_OUTPUT_CHARS]

    @staticmethod
    def _clean(rewritten: str) -> str:
        """One line, no quotes, short enough to be a query."""
        cleaned = rewritten.strip().strip('"').strip()
        if not cleaned:
            return ""
        cleaned = cleaned.splitlines()[0].strip()
        if len(cleaned) > MAX_OUTPUT_CHARS or not any(char.isalnum() for char in cleaned):
            return ""
        return cleaned

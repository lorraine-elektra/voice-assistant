"""Canned replies so the whole app runs with no API keys."""
import asyncio
from typing import AsyncIterator

from app.config import settings

# A message with one of these words gets a fake web search.
SEARCH_WORDS = ("weather", "news", "latest", "today", "price", "score", "look up", "search")
# A search message with this word gets a fake search that fails.
FAIL_WORD = "unreachable"
MOCK_SOURCE = {"title": "Example News (mock result)", "url": "https://example.com/mock-result"}


async def _stream_words(reply: str) -> AsyncIterator[dict]:
    """Send the reply a word at a time, the way a real model streams."""
    for word in reply.split(" "):
        yield {"type": "text", "text": word + " "}
        await asyncio.sleep(settings.mock_word_delay)


async def mock_reply(history: list[dict]) -> AsyncIterator[dict]:
    said = history[-1]["content"].strip().rstrip(".!?")
    lower = said.lower()
    sources = None
    if any(word in lower for word in SEARCH_WORDS):
        yield {"type": "searching"}
        await asyncio.sleep(settings.mock_search_delay)
        if FAIL_WORD in lower:
            yield {"type": "search_failed", "reason": "unavailable"}
            reply = (
                "I could not look that up just now. "
                "From what I already know, this is a mock answer."
            )
        else:
            sources = [MOCK_SOURCE]
            reply = (
                "According to Example News, this is a canned search result. "
                "Add your Gemini key to get real web answers."
            )
        yield {"type": "search_done"}
    else:
        reply = (
            f"This is a mock reply. You said: {said}. "
            "Add your Gemini key to hear real answers."
        )
    async for event in _stream_words(reply):
        yield event
    if sources:
        yield {"type": "sources", "sources": sources}

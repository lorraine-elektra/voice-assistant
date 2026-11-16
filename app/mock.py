"""Canned replies so the whole app runs with no API keys."""
import asyncio
from typing import AsyncIterator

from app.config import settings


async def _stream_words(reply: str) -> AsyncIterator[dict]:
    """Send the reply a word at a time, the way a real model streams."""
    for word in reply.split(" "):
        yield {"type": "text", "text": word + " "}
        await asyncio.sleep(settings.mock_word_delay)


async def mock_reply(history: list[dict]) -> AsyncIterator[dict]:
    said = history[-1]["content"].strip().rstrip(".!?")
    reply = (
        f"This is a mock reply. You said: {said}. "
        "Add your Anthropic key to hear real answers."
    )
    async for event in _stream_words(reply):
        yield event

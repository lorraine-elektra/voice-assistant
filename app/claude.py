"""Streams a reply from Claude as a series of events."""
from typing import AsyncIterator

import anthropic

from app.config import settings
from app.prompts import SYSTEM_PROMPT

REFUSAL_TEXT = "Sorry, I can't help with that one."
_client = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def claude_reply(history: list[dict]) -> AsyncIterator[dict]:
    async with get_client().messages.stream(
        model=settings.anthropic_model,
        max_tokens=4096,  # spoken replies are a few sentences, this leaves room to think
        system=SYSTEM_PROMPT,
        output_config={"effort": settings.anthropic_effort},
        messages=history,
    ) as stream:
        async for text in stream.text_stream:
            yield {"type": "text", "text": text}
        final = await stream.get_final_message()
    if final.stop_reason == "refusal":
        yield {"type": "text", "text": REFUSAL_TEXT}

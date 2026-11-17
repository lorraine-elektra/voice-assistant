"""Streams a reply from Claude as a series of events (see app/brain.py for the list)."""
from datetime import date
from typing import AsyncIterator

import anthropic

from app.config import settings
from app.languages import DEFAULT, Language
from app.prompts import system_prompt

REFUSAL_TEXT = "Sorry, I can't help with that one."
MAX_SOURCES = 4
MAX_CONTINUES = 3  # how many times we resume a reply the API paused mid search
_client = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def web_search_tool() -> dict:
    """Anthropic's built in web search. It runs on Anthropic's side, we only switch it on.
    The basic version works on every model and adds the least waiting time.
    Docs: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
    """
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": settings.web_search_max_uses,
    }


async def claude_reply(history: list[dict], language: Language = DEFAULT) -> AsyncIterator[dict]:
    messages = list(history)
    sources: dict[str, str] = {}  # url -> title, only pages the answer really cites
    for _ in range(MAX_CONTINUES):
        async with get_client().messages.stream(
            model=settings.anthropic_model,
            max_tokens=4096,  # spoken replies are short, this leaves room to think
            system=f"{system_prompt(language)}\n\nToday's date is {date.today():%A %d %B %Y}.",
            output_config={"effort": settings.anthropic_effort},
            tools=[web_search_tool()],
            messages=messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "server_tool_use" and block.name == "web_search":
                        yield {"type": "searching"}
                    elif block.type == "web_search_tool_result":
                        # A list means results. Anything else is an error object.
                        if not isinstance(block.content, list):
                            yield {"type": "search_failed", "reason": block.content.error_code}
                        yield {"type": "search_done"}
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "text", "text": event.delta.text}
                    elif event.delta.type == "citations_delta":
                        url = getattr(event.delta.citation, "url", None)
                        if url:
                            sources.setdefault(url, event.delta.citation.title or url)
            final = await stream.get_final_message()
        if final.stop_reason != "pause_turn":
            break
        # The API paused a long search. Send its message back unchanged to carry on.
        messages.append({"role": "assistant", "content": final.content})
    if final.stop_reason == "refusal":
        yield {"type": "text", "text": REFUSAL_TEXT}
    if sources:
        links = [{"title": title, "url": url} for url, title in sources.items()]
        yield {"type": "sources", "sources": links[:MAX_SOURCES]}

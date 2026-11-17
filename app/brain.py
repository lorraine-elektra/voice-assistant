"""Picks who answers: real Gemini, or the mock when there is no key.

Both produce the same events, so the rest of the app does not care which one ran:
  {"type": "language", "language": "tw"}     which language the reply is in (real Gemini only)
  {"type": "text", "text": "..."}            a piece of the reply
  {"type": "searching"}                      a web search has started
  {"type": "search_failed", "reason": "..."} that search did not work
  {"type": "search_done"}                    the search is over, the answer follows
  {"type": "sources", "sources": [{"title": "...", "url": "..."}]}
"""
from typing import AsyncIterator

from app.gemini import gemini_reply
from app.config import settings
from app.languages import DEFAULT, Language
from app.mock import mock_reply


def reply_events(history: list[dict], language: Language = DEFAULT, name: str = "") -> AsyncIterator[dict]:
    if settings.brain_mode == "gemini":
        return gemini_reply(history, language, name)
    return mock_reply(history)

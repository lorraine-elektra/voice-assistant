"""Picks who answers: real Claude, or the mock when there is no key.

Both produce the same events, so the rest of the app does not care which one ran:
  {"type": "text", "text": "..."}   a piece of the reply
"""
from typing import AsyncIterator

from app.claude import claude_reply
from app.config import settings
from app.mock import mock_reply


def reply_events(history: list[dict]) -> AsyncIterator[dict]:
    if settings.brain_mode == "claude":
        return claude_reply(history)
    return mock_reply(history)

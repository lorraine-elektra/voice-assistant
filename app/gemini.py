"""Streams a reply from Gemini as events (see app/brain.py for the list).

Gemini answers with JSON: {"detected_language": "...", "reply_text": "..."}. The language
comes first, so we learn it before the first word and can still speak sentence by sentence.
Docs: https://ai.google.dev/gemini-api/docs/structured-output
"""
import json
import re
from datetime import date
from typing import AsyncIterator

import httpx

from app.config import settings
from app.languages import DEFAULT, LANGUAGES, Language
from app.prompts import system_prompt

API = "https://generativelanguage.googleapis.com/v1beta/models"
REFUSAL_TEXT = "Sorry, I can't help with that one."
BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}
_client = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30)
    return _client


def json_rules() -> str:
    ids = ", ".join(LANGUAGES)
    return (
        "Answer as JSON with two fields. detected_language is the language your reply is "
        f"written in, exactly one of: {ids}. reply_text is the reply to read aloud."
    )


def request_body(history: list[dict], language: Language, name: str = "") -> dict:
    system = f"{system_prompt(language, name)}\n\n{json_rules()}\n\nToday's date is {date.today():%A %d %B %Y}."
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {"role": "user" if turn["role"] == "user" else "model", "parts": [{"text": turn["content"]}]}
            for turn in history
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "detected_language": {"type": "STRING", "enum": list(LANGUAGES)},
                    "reply_text": {"type": "STRING"},
                },
                "required": ["detected_language", "reply_text"],
                "propertyOrdering": ["detected_language", "reply_text"],
            },
            "thinkingConfig": {"thinkingBudget": 0},  # no thinking: voice needs the first word fast
        },
    }


_LANGUAGE = re.compile(r'"detected_language"\s*:\s*"([^"]*)"')
_REPLY = re.compile(r'"reply_text"\s*:\s*"')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}


class ReplyExtractor:
    """Reads the JSON as it streams in. feed() returns (language or None, new reply text)."""

    def __init__(self) -> None:
        self.buffer = ""
        self.language: str | None = None
        self.pos: int | None = None  # where we have read up to inside reply_text
        self.done = False

    def feed(self, chunk: str) -> tuple[str | None, str]:
        self.buffer += chunk
        found = None
        if self.language is None and (match := _LANGUAGE.search(self.buffer)):
            self.language = found = match.group(1)
        if self.pos is None and (match := _REPLY.search(self.buffer)):
            self.pos = match.end()
        out: list[str] = []
        if self.pos is not None and not self.done:
            text, i = self.buffer, self.pos
            while i < len(text):
                char = text[i]
                if char == '"':
                    self.done = True
                    break
                if char != "\\":
                    out.append(char)
                    i += 1
                elif i + 1 >= len(text):
                    break  # the escape is split across chunks, wait for the rest
                elif text[i + 1] == "u":
                    if i + 6 > len(text):
                        break
                    out.append(chr(int(text[i + 2:i + 6], 16)))
                    i += 6
                else:
                    out.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
            self.pos = i
        return found, "".join(out)


async def gemini_reply(history: list[dict], language: Language = DEFAULT, name: str = "") -> AsyncIterator[dict]:
    url = f"{API}/{settings.gemini_model}:streamGenerateContent?alt=sse"
    headers = {"x-goog-api-key": settings.gemini_api_key}
    extractor = ReplyExtractor()
    spoke = False
    async with get_client().stream("POST", url, headers=headers, json=request_body(history, language, name)) as response:
        if response.status_code != 200:
            await response.aread()
            response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = json.loads(line[5:])
            candidate = (data.get("candidates") or [{}])[0]
            for part in candidate.get("content", {}).get("parts", []):
                found, text = extractor.feed(part.get("text", ""))
                if found in LANGUAGES:
                    yield {"type": "language", "language": found}
                if text:
                    spoke = True
                    yield {"type": "text", "text": text}
    if not spoke:  # blocked, or nothing usable came back
        yield {"type": "text", "text": REFUSAL_TEXT}

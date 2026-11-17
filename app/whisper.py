"""Groq speech to text (Whisper). The browser sends one recorded phrase, we send it on.
Docs: https://console.groq.com/docs/speech-to-text
"""
from dataclasses import dataclass

import httpx

from app.config import settings

API = "https://api.groq.com/openai/v1/audio/transcriptions"
MIN_AVG_LOGPROB = -1.0       # Whisper's own rule of thumb: lower means it was guessing
MAX_COMPRESSION_RATIO = 2.4  # higher means repeated, garbled words


@dataclass
class Heard:
    text: str
    language: str       # what Whisper thinks the language was
    confident: bool     # false when Whisper was guessing, which is when Twi gets a second opinion


def is_confident(segments: list[dict]) -> bool:
    return all(
        segment.get("avg_logprob", 0) > MIN_AVG_LOGPROB
        and segment.get("compression_ratio", 0) < MAX_COMPRESSION_RATIO
        for segment in segments
    )


async def transcribe(http: httpx.AsyncClient, audio: bytes, mime: str = "audio/wav") -> Heard:
    """Returns the words in the recording. No language is sent, so Whisper detects it."""
    response = await http.post(
        API,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        files={"file": ("speech", audio, mime)},
        data={"model": settings.groq_model, "response_format": "verbose_json", "temperature": "0"},
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    return Heard(
        text=body.get("text", "").strip(),
        language=body.get("language", ""),
        confident=is_confident(body.get("segments", [])),
    )

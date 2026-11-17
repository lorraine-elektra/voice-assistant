"""Abena AI: Twi and Pidgin text to speech, and Twi speech to text.
Docs: https://abena.mobobi.com/playground/sdk/docs/
"""
import base64

import httpx

from app.config import settings

TTS_API = "https://abena.mobobi.com/playground/api/v1/tts/synthesize/"
ASR_API = "https://abena.mobobi.com/playground/api/v1/asr/transcribe/"
MAX_CHARS = 500  # the longest text Abena speaks in one request
MIME = "audio/wav"
# Which Abena recogniser to use for each of our language ids.
ASR_LANGUAGES = {"tw": "twi-en", "en": "en", "pcm-GH": "gpe", "pcm-NG": "pcm"}


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.abena_api_key}"}


async def synthesize(http: httpx.AsyncClient, text: str, voice: str) -> bytes:
    """Returns the sentence as WAV audio. Raises if it is too long, refused or down."""
    if len(text) > MAX_CHARS:
        raise ValueError(f"Abena speaks at most {MAX_CHARS} characters, got {len(text)}")
    response = await http.post(TTS_API, headers=_headers(), json={"text": text, "voice": voice}, timeout=30)
    response.raise_for_status()
    return base64.b64decode(response.json()["audio_base64"])


async def transcribe(http: httpx.AsyncClient, audio: bytes, mime: str = "audio/webm", language_id: str = "tw") -> str:
    """Returns the words in a recording. Meant as the second opinion for Twi."""
    response = await http.post(
        ASR_API,
        headers=_headers(),
        files={"audio_file": ("speech", audio, mime)},
        data={"language": ASR_LANGUAGES.get(language_id, "twi-en")},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    return (body.get("transcription") or body.get("text") or "").strip()

"""Abena AI: text to speech and speech to text for Twi and both Pidgins.
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
ASR_LANGUAGES = {"tw": "twi-en", "pcm-GH": "gpe", "pcm-NG": "pcm"}
# Languages where Abena listens for the user. The browser listens for the others.
LISTENS_FOR = tuple(ASR_LANGUAGES)


def _headers() -> dict:
    # The playground API needs no key. Send one only if the owner set it.
    return {"Authorization": f"Bearer {settings.abena_api_key}"} if settings.abena_api_key else {}


async def synthesize(http: httpx.AsyncClient, text: str, voice: str) -> bytes:
    """Returns the sentence as WAV audio. Raises if it is too long, refused or down."""
    if len(text) > MAX_CHARS:
        raise ValueError(f"Abena speaks at most {MAX_CHARS} characters, got {len(text)}")
    response = await http.post(TTS_API, headers=_headers(), json={"text": text, "voice": voice}, timeout=30)
    response.raise_for_status()
    return base64.b64decode(response.json()["audio_base64"])


async def transcribe(http: httpx.AsyncClient, audio: bytes, mime: str = "audio/webm", language_id: str = "tw") -> str:
    """Returns the words in a recording of Twi or Pidgin."""
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

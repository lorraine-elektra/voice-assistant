"""ElevenLabs text to speech. One request per sentence, the key stays on the backend.
Docs: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
"""
import httpx

from app.config import settings

API = "https://api.elevenlabs.io/v1/text-to-speech"


async def synthesize(http: httpx.AsyncClient, text: str) -> bytes:
    """Returns the sentence as MP3 audio. Raises if ElevenLabs refuses or is down."""
    body = {"text": text}
    if settings.elevenlabs_model:
        body["model_id"] = settings.elevenlabs_model
    response = await http.post(
        f"{API}/{settings.elevenlabs_voice_id}",
        headers={"xi-api-key": settings.elevenlabs_api_key},
        json=body,
        timeout=20,
    )
    response.raise_for_status()
    return response.content

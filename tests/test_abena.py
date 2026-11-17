"""Abena AI, faked. No keys, no network."""
import asyncio
import base64
import json

import httpx
import pytest

from app import abena
from app.config import settings
from tests.conftest import read_until


@pytest.fixture
def abena_key(monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")


def call(handler, coroutine):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await coroutine(http)

    return asyncio.run(run())


# ---------- which voice speaks ----------

def test_mock_mode_means_no_abena_voice():
    assert not settings.abena_mode and settings.abena_voice("tw") == ""


def test_abena_works_without_a_key_and_sends_no_auth_header(monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "abena_api_key", "")
    assert settings.abena_mode and settings.abena_voice("tw") == "abena_twi_medium"
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        return httpx.Response(200, json={"audio_base64": base64.b64encode(b"RIFF").decode()})

    assert call(handler, lambda http: abena.synthesize(http, "Hi", "abena_twi_medium")) == b"RIFF"
    assert "authorization" not in seen["headers"]


def test_abena_speaks_twi_and_pidgin_only(abena_key):
    assert settings.abena_voice("tw") == "abena_twi_medium"
    assert settings.abena_voice("pcm-GH") == "kobby_gpe_medium"
    assert settings.abena_voice("pcm-NG") == "james_pcm_medium"
    assert settings.abena_voice("tw", "Kofi") == "kofi_twi_medium"
    assert settings.abena_voice("en") == settings.abena_voice("fr") == settings.abena_voice("auto") == ""


def test_mock_mode_ignores_the_abena_key(abena_key, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", True)
    assert settings.abena_voice("tw") == ""


def test_ready_says_whether_abena_is_on_but_never_shows_the_key(client, abena_key):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert ready["abena"] is True and "ab-test" not in json.dumps(ready)


# ---------- text to speech ----------

def test_synthesize_sends_text_and_voice_and_decodes_the_wav(abena_key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content))
        return httpx.Response(200, json={
            "status": "success", "audio_base64": base64.b64encode(b"RIFFwav").decode(), "mime_type": "audio/wav",
        })

    wav = call(handler, lambda http: abena.synthesize(http, "Akwaaba.", "abena_twi_medium"))
    assert wav == b"RIFFwav"
    assert seen == {
        "url": "https://abena.mobobi.com/playground/api/v1/tts/synthesize/",
        "auth": "Bearer ab-test",
        "body": {"text": "Akwaaba.", "voice": "abena_twi_medium"},
    }


def test_text_over_500_characters_is_refused_before_any_request(abena_key):
    def handler(request):
        raise AssertionError("no request should be sent")

    with pytest.raises(ValueError):
        call(handler, lambda http: abena.synthesize(http, "a" * 501, "abena_twi_medium"))


def test_rate_limit_is_raised(abena_key):
    with pytest.raises(httpx.HTTPStatusError):
        call(lambda request: httpx.Response(429), lambda http: abena.synthesize(http, "Hi.", "abena_twi_medium"))


def reply_in(client, monkeypatch, language, message):
    """Runs one turn where Gemini says the reply is in `language`."""
    async def fake(history, lang):
        yield {"type": "language", "language": language}
        yield {"type": "text", "text": "Ɛte sɛn?"}

    async def fake_abena(http, text, voice):
        return f"{voice}:{text}".encode()

    monkeypatch.setattr("app.session.reply_events", fake)
    monkeypatch.setattr(abena, "synthesize", fake_abena)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": message})
        return read_until(ws, "done")


def test_twi_reply_is_spoken_by_abena_as_wav(client, abena_key, monkeypatch):
    messages = reply_in(client, monkeypatch, "tw", "hello")
    sentence = next(m for m in messages if m["type"] == "sentence")
    audio = next(m for m in messages if m["type"] == "audio")
    assert sentence["audio_expected"] is True
    assert audio["mime"] == "audio/wav"
    assert base64.b64decode(audio["audio"]).decode() == "abena_twi_medium:Ɛte sɛn?"


def test_english_reply_stays_with_the_browser_voice(client, abena_key, monkeypatch):
    messages = reply_in(client, monkeypatch, "en", "hello")
    assert next(m for m in messages if m["type"] == "sentence")["audio_expected"] is False
    assert not [m for m in messages if m["type"] == "audio"]


def test_failed_abena_audio_falls_back_to_the_browser_voice(client, abena_key, monkeypatch):
    async def fake(history, lang):
        yield {"type": "language", "language": "pcm-NG"}
        yield {"type": "text", "text": "How far?"}

    async def broken(http, text, voice):
        raise httpx.ConnectError("Abena is down")

    monkeypatch.setattr("app.session.reply_events", fake)
    monkeypatch.setattr(abena, "synthesize", broken)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    audio = next(m for m in messages if m["type"] == "audio")
    assert audio["audio"] is None and audio["mime"] is None


# ---------- speech to text ----------

def test_transcribe_sends_the_recording_as_audio_file_with_a_language(abena_key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=request.content)
        return httpx.Response(200, json={"text": "Mepɛ sɛ", "transcription": " Mepɛ sɛ mede ", "language": "twi-en"})

    text = call(handler, lambda http: abena.transcribe(http, b"audio-bytes", "audio/webm", "tw"))
    assert text == "Mepɛ sɛ mede"
    assert seen["url"] == "https://abena.mobobi.com/playground/api/v1/asr/transcribe/"
    assert seen["auth"] == "Bearer ab-test"
    assert b'name="audio_file"' in seen["body"] and b"audio-bytes" in seen["body"] and b"twi-en" in seen["body"]


# ---------- Abena listens for Twi and Pidgin when there is no Whisper key ----------

def hear_with_abena(client, language, fake):
    import base64 as b64

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "settings", "language": language, "voice": ""})
        ws.send_json({"type": "phrase", "mime": "audio/wav", "audio": b64.b64encode(b"RIFFpcm").decode()})
        return ws.receive_json()


def test_without_groq_abena_hears_twi(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "groq_api_key", "")
    asked = {}

    async def fake(http, audio, mime, language_id):
        asked["language"] = language_id
        return "Ɛte sɛn?"

    monkeypatch.setattr(abena, "transcribe", fake)
    assert hear_with_abena(client, "tw", fake) == {"type": "transcript", "text": "Ɛte sɛn?", "final": True}
    assert asked["language"] == "tw"


def test_without_groq_other_languages_are_not_sent_to_abena(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "groq_api_key", "")

    async def never(*args):
        raise AssertionError("Abena should not be called for English")

    monkeypatch.setattr(abena, "transcribe", never)
    assert hear_with_abena(client, "en", never)["type"] == "error"


def test_abena_limit_gives_a_clear_message(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "groq_api_key", "")

    async def refused(http, audio, mime, language_id):
        request = httpx.Request("POST", abena.ASR_API)
        raise httpx.HTTPStatusError("limit", request=request, response=httpx.Response(429, request=request))

    monkeypatch.setattr(abena, "transcribe", refused)
    reply = hear_with_abena(client, "tw", refused)
    assert reply["type"] == "error" and "type your message" in reply["message"]

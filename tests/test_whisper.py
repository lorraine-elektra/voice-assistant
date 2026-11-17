"""Groq Whisper, the Abena second opinion and the voice choices. All faked, no keys."""
import asyncio
import base64
import json

import httpx
import pytest

from app import abena, whisper
from app.abena_voices import voice_id
from app.config import settings
from tests.conftest import read_until

CLEAR = {"avg_logprob": -0.2, "compression_ratio": 1.4}
GUESSING = {"avg_logprob": -1.6, "compression_ratio": 1.4}


@pytest.fixture
def whisper_key(monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "groq_api_key", "gq-test")
    monkeypatch.setattr(settings, "groq_model", "whisper-large-v3")


def phrase(audio=b"RIFFpcm"):
    return {"type": "phrase", "mime": "audio/wav", "audio": base64.b64encode(audio).decode()}


def hear(client, fake_whisper, message=None):
    """Sends one phrase and returns the first thing the backend says about it."""
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json(message or phrase())
        return ws.receive_json()


# ---------- which mode ----------

def test_groq_key_switches_listening_to_whisper(client, whisper_key):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert ready["stt"] == "whisper" and "gq-test" not in json.dumps(ready)


def test_no_groq_key_means_the_browser_listens(client, whisper_key, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["stt"] == "browser"


# ---------- the Groq request ----------

def test_whisper_sends_the_recording_and_reads_confidence(whisper_key):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=request.content)
        return httpx.Response(200, json={"text": "  wetin dey happen  ", "language": "english", "segments": [CLEAR]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await whisper.transcribe(http, b"audio-bytes")

    assert asyncio.run(run()) == whisper.Heard("wetin dey happen", "english", True)
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer gq-test"
    assert b"audio-bytes" in seen["body"] and b"whisper-large-v3" in seen["body"]
    assert b'name="language"' not in seen["body"]  # Whisper detects the language itself


def test_guessing_and_garbled_segments_are_not_confident():
    assert whisper.is_confident([CLEAR, CLEAR]) and whisper.is_confident([])
    assert not whisper.is_confident([CLEAR, GUESSING])
    assert not whisper.is_confident([{"avg_logprob": -0.2, "compression_ratio": 3.0}])


# ---------- a phrase through the backend ----------

def fake_whisper(monkeypatch, heard):
    async def fake(http, audio, mime):
        fake.got = (audio, mime)
        return heard

    monkeypatch.setattr(whisper, "transcribe", fake)
    return fake


def test_a_phrase_becomes_a_final_transcript(client, whisper_key, monkeypatch):
    fake = fake_whisper(monkeypatch, whisper.Heard("How far?", "english", True))
    assert hear(client, fake) == {"type": "transcript", "text": "How far?", "final": True}
    assert fake.got == (b"RIFFpcm", "audio/wav")


def test_a_guess_gets_abena_as_a_second_opinion(client, whisper_key, monkeypatch):
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")
    fake_whisper(monkeypatch, whisper.Heard("mm pe se", "shona", False))
    asked = {}

    async def fake_abena(http, audio, mime, language_id):
        asked["language"] = language_id
        return "Mepɛ sɛ mede sika"

    monkeypatch.setattr(abena, "transcribe", fake_abena)
    assert hear(client, None)["text"] == "Mepɛ sɛ mede sika"
    assert asked["language"] == "tw"


def test_a_confident_phrase_does_not_use_up_abena_credits(client, whisper_key, monkeypatch):
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")
    fake_whisper(monkeypatch, whisper.Heard("hello", "english", True))

    async def never(*args):
        raise AssertionError("Abena should not be called")

    monkeypatch.setattr(abena, "transcribe", never)
    assert hear(client, None)["text"] == "hello"


def test_if_abena_fails_whispers_words_are_kept(client, whisper_key, monkeypatch):
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")
    fake_whisper(monkeypatch, whisper.Heard("mm pe se", "shona", False))

    async def broken(*args):
        raise httpx.ConnectError("Abena is down")

    monkeypatch.setattr(abena, "transcribe", broken)
    assert hear(client, None)["text"] == "mm pe se"


def test_a_failed_transcription_is_a_friendly_error(client, whisper_key, monkeypatch):
    async def broken(http, audio, mime):
        raise httpx.ConnectError("Groq is down")

    monkeypatch.setattr(whisper, "transcribe", broken)
    reply = hear(client, None)
    assert reply["type"] == "error" and "turn" not in reply


def test_the_transcript_can_start_a_turn_like_typed_text(client, whisper_key, monkeypatch):
    fake_whisper(monkeypatch, whisper.Heard("hello", "english", True))
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json(phrase())
        assert ws.receive_json()["final"] is True
        ws.send_json({"type": "user_text", "text": "hello"})
        assert read_until(ws, "done")[-1]["turn"] == 1


# ---------- the Abena voices on the page ----------

def test_voice_can_be_chosen_by_name_or_by_gender():
    assert voice_id("tw") == "abena_twi_medium"            # the default
    assert voice_id("tw", "Kofi") == "kofi_twi_medium"
    assert voice_id("tw", "man") == "kofi_twi_medium"
    assert voice_id("tw", "woman") == "abena_twi_medium"
    assert voice_id("pcm-NG", "woman") == "chioma_eng"
    assert voice_id("pcm-GH", "nobody") == "kobby_gpe_medium"
    assert voice_id("en", "woman") == ""                    # Abena does not speak English here


def test_ready_lists_abena_voice_names_but_never_ids(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    twi = ready["abena_voices"]["tw"]
    assert {v["gender"] for v in twi} == {"woman", "man"}
    assert "Kofi" in [v["name"] for v in twi]
    assert "twi_medium" not in json.dumps(ready)


def test_no_abena_key_means_no_abena_voices(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["abena_voices"] == {}


def test_chosen_abena_voice_speaks_the_reply(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")

    async def fake_reply(history, language):
        yield {"type": "language", "language": "tw"}
        yield {"type": "text", "text": "Ɛte sɛn?"}

    async def fake_abena(http, text, voice):
        return voice.encode()

    monkeypatch.setattr("app.session.reply_events", fake_reply)
    monkeypatch.setattr(abena, "synthesize", fake_abena)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        for choice, expected in (("Kofi", "kofi_twi_medium"), ("woman", "abena_twi_medium")):
            ws.send_json({"type": "settings", "language": "auto", "voice": choice})
            ws.send_json({"type": "user_text", "text": "hello"})
            audio = [m["audio"] for m in read_until(ws, "done") if m["type"] == "audio"]
            assert [base64.b64decode(a).decode() for a in audio] == [expected]

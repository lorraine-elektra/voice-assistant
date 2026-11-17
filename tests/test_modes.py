"""Which services are active, speech failures, and the latency log. All faked, no keys."""
import asyncio
import base64
import json
import time

import httpx
import pytest

from app import abena
from app.config import settings
from tests.conftest import read_until


@pytest.fixture
def real_voice(monkeypatch):
    """Pretend the Groq and Abena keys are set. The brain stays on the mock (no Gemini key)."""
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "groq_api_key", "gq-test")
    monkeypatch.setattr(settings, "abena_api_key", "ab-test")


def test_no_keys_means_everything_runs_in_the_browser_and_mock(client):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert (ready["brain"], ready["stt"], ready["tts"], ready["abena"]) == ("mock", "browser", "browser", False)


def test_keys_switch_on_the_real_services_but_never_reach_the_browser(client, real_voice, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "gm-test")
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert (ready["brain"], ready["stt"], ready["tts"]) == ("gemini", "whisper", "abena")
    assert not {"gq-test", "ab-test", "gm-test"} & set(json.dumps(ready).replace('"', " ").split())
    assert "-test" not in json.dumps(ready)


def test_mock_mode_ignores_keys(client, real_voice, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", True)
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert (ready["stt"], ready["tts"]) == ("browser", "browser")


def tw_reply(monkeypatch, synthesize):
    async def fake_reply(history, language, name=""):
        yield {"type": "language", "language": "tw"}
        yield {"type": "text", "text": "Ɛte sɛn? Me ho yɛ."}

    monkeypatch.setattr("app.session.reply_events", fake_reply)
    monkeypatch.setattr(abena, "synthesize", synthesize)


def test_every_sentence_gets_audio_before_done(client, real_voice, monkeypatch):
    async def fake(http, text, voice):
        return text.encode()

    tw_reply(monkeypatch, fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    sentences = {m["index"]: m["text"] for m in messages if m["type"] == "sentence"}
    audio = {m["index"]: base64.b64decode(m["audio"]).decode() for m in messages if m["type"] == "audio"}
    assert len(sentences) == 2 and audio == sentences


def test_failed_audio_falls_back_to_the_browser_voice(client, real_voice, monkeypatch):
    async def broken(http, text, voice):
        raise httpx.ConnectError("Abena is down")

    tw_reply(monkeypatch, broken)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    audio = [m for m in messages if m["type"] == "audio"]
    assert len(audio) == 2 and all(m["audio"] is None for m in audio)


def test_barge_in_drops_audio_still_being_prepared(client, real_voice, monkeypatch):
    async def slow(http, text, voice):
        await asyncio.sleep(30)

    tw_reply(monkeypatch, slow)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        read_until(ws, "sentence")
        started = time.monotonic()
        ws.send_json({"type": "stop"})
        tail = read_until(ws, "cancelled")
        assert time.monotonic() - started < 5
        assert not [m for m in tail if m["type"] == "audio"]


def test_stray_binary_audio_is_ignored(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_bytes(b"\x01\x02")
        ws.send_json({"type": "user_text", "text": "hi"})
        assert read_until(ws, "done")[-1]["turn"] == 1


def test_latency_report_is_logged(client, caplog):
    caplog.set_level("INFO", logger="voice")
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "latency", "turn": 1, "ms": 840, "searched": False})
        ws.send_json({"type": "user_text", "text": "hi"})
        read_until(ws, "done")
    assert "840 ms from end of speech to first spoken word" in caplog.text

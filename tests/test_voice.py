"""Deepgram and ElevenLabs, with both services faked. No keys, no network."""
import asyncio
import base64
import json
import time

import httpx
import pytest

from app import stt, tts
from app.config import settings
from tests.conftest import read_until


@pytest.fixture
def voice_keys(monkeypatch):
    """Pretend the voice keys are set. The brain stays on the mock (no Anthropic key)."""
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "deepgram_api_key", "dg-test")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "el-test")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "voice-test")


# ---------- which mode is active ----------

def test_no_keys_means_browser_voice(client):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert (ready["brain"], ready["stt"], ready["tts"], ready["voices"]) == ("mock", "browser", "browser", [])


def test_keys_switch_on_real_voice_but_never_reach_the_browser(client, voice_keys):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert (ready["brain"], ready["stt"], ready["tts"]) == ("mock", "deepgram", "elevenlabs")
    assert "test" not in json.dumps(ready)


def test_mock_mode_ignores_keys(client, voice_keys, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", True)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["tts"] == "browser"


# ---------- ElevenLabs ----------

def test_synthesize_sends_one_sentence_with_the_key_in_a_header(voice_keys):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), key=request.headers["xi-api-key"], body=json.loads(request.content))
        return httpx.Response(200, content=b"mp3-bytes")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await tts.synthesize(http, "Hello there.", "voice-test")

    assert asyncio.run(run()) == b"mp3-bytes"
    assert seen == {
        "url": "https://api.elevenlabs.io/v1/text-to-speech/voice-test",
        "key": "el-test",
        "body": {"text": "Hello there."},
    }


def test_every_sentence_gets_audio_before_done(client, voice_keys, monkeypatch):
    async def fake(http, text, voice_id):
        return text.encode()

    monkeypatch.setattr(tts, "synthesize", fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    sentences = {m["index"]: m["text"] for m in messages if m["type"] == "sentence"}
    audio = {m["index"]: base64.b64decode(m["audio"]).decode() for m in messages if m["type"] == "audio"}
    assert len(sentences) == 3 and audio == sentences


def test_failed_audio_falls_back_to_the_browser_voice(client, voice_keys, monkeypatch):
    async def broken(http, text, voice_id):
        raise httpx.ConnectError("ElevenLabs is down")

    monkeypatch.setattr(tts, "synthesize", broken)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    audio = [m for m in messages if m["type"] == "audio"]
    assert len(audio) == 3 and all(m["audio"] is None for m in audio)


def test_barge_in_drops_audio_still_being_prepared(client, voice_keys, monkeypatch):
    async def slow(http, text, voice_id):
        await asyncio.sleep(30)

    monkeypatch.setattr(tts, "synthesize", slow)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        read_until(ws, "sentence")
        started = time.monotonic()
        ws.send_json({"type": "stop"})
        tail = read_until(ws, "cancelled")
        assert time.monotonic() - started < 5
        assert not [m for m in tail if m["type"] == "audio"]


# ---------- Deepgram ----------

class FakeDeepgram:
    """Stands in for the Deepgram WebSocket."""

    def __init__(self, replies=()):
        self.sent, self.closed = [], False
        self.inbox = asyncio.Queue()
        for reply in replies:
            self.inbox.put_nowait(json.dumps(reply))

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.inbox.get()


def results(text, is_final=False, speech_final=False):
    return {
        "type": "Results", "is_final": is_final, "speech_final": speech_final,
        "channel": {"alternatives": [{"transcript": text}]},
    }


def test_deepgram_url_uses_settings(monkeypatch):
    monkeypatch.setattr(settings, "deepgram_model", "nova-3")
    url = stt.deepgram_url(16000)
    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "model=nova-3" in url and "sample_rate=16000" in url and "encoding=linear16" in url


def test_relay_joins_pieces_into_one_final_phrase():
    heard = []

    async def on_transcript(text, final):
        heard.append((text, final))

    async def run():
        relay = stt.DeepgramRelay(on_transcript, None)
        for message in (
            results("what is"),
            results("What is the", is_final=True),
            results("weather"),
            results("weather today?", is_final=True, speech_final=True),
            results("", is_final=True, speech_final=True),  # silence: nothing to report
            results("one more", is_final=True),
            {"type": "UtteranceEnd"},  # backup end signal
        ):
            await relay.handle(message)

    asyncio.run(run())
    assert heard == [
        ("what is", False),
        ("What is the weather", False),
        ("What is the weather today?", True),
        ("one more", True),
    ]


def test_audio_goes_to_deepgram_and_words_come_back(client, voice_keys, monkeypatch):
    fake = FakeDeepgram([results("hello"), results("Hello there.", is_final=True, speech_final=True)])
    seen = {}

    async def fake_connect(url, additional_headers):
        seen.update(url=url, headers=additional_headers)
        return fake

    monkeypatch.setattr(stt, "connect", fake_connect)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_start", "sample_rate": 16000})
        ws.send_bytes(b"\x01\x02")
        assert ws.receive_json() == {"type": "transcript", "text": "hello", "final": False}
        assert ws.receive_json() == {"type": "transcript", "text": "Hello there.", "final": True}
        ws.send_json({"type": "audio_stop"})
        ws.send_json({"type": "user_text", "text": "hi"})  # proves audio_stop was handled
        read_until(ws, "done")
    assert seen["headers"] == {"Authorization": "Token dg-test"}
    assert b"\x01\x02" in fake.sent and fake.closed


def test_deepgram_without_a_key_tells_the_browser_to_fall_back(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_start", "sample_rate": 16000})
        assert ws.receive_json()["type"] == "stt_failed"


def test_deepgram_connection_error_tells_the_browser_to_fall_back(client, voice_keys, monkeypatch):
    async def refuse(url, additional_headers):
        raise OSError("no network")

    monkeypatch.setattr(stt, "connect", refuse)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_start", "sample_rate": 16000})
        assert ws.receive_json()["type"] == "stt_failed"


def test_latency_report_is_logged(client, caplog):
    caplog.set_level("INFO", logger="voice")
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "latency", "turn": 1, "ms": 840, "searched": False})
        ws.send_json({"type": "user_text", "text": "hi"})
        read_until(ws, "done")
    assert "840 ms from end of speech to first spoken word" in caplog.text

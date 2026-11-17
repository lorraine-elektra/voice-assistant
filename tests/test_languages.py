"""The language and voice choices. No keys, no network."""
import asyncio
import base64
import json

from app import claude, stt, tts
from app.config import settings
from app.languages import LANGUAGES
from app.prompts import system_prompt
from tests.conftest import read_until
from tests.test_search import FakeClient, FakeStream, text
from tests.test_voice import FakeDeepgram, voice_keys  # noqa: F401 (a fixture)


def test_ready_lists_the_six_languages(client):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert [lang["name"] for lang in ready["languages"]] == [
        "English", "Spanish", "French", "Naija Pidgin", "Ghana Pidgin", "Ghana Twi",
    ]
    assert all(lang["id"] and lang["browser"] for lang in ready["languages"])


def test_every_language_tells_claude_what_to_speak():
    for language in LANGUAGES.values():
        assert language.instruction in system_prompt(language)
    assert "Nigerian Pidgin" in system_prompt(LANGUAGES["pcm-NG"])
    assert "Twi" in system_prompt(LANGUAGES["tw"])


def test_claude_gets_the_chosen_language(monkeypatch):
    fake = FakeClient(FakeStream([text("Bonjour.")], "end_turn"))
    monkeypatch.setattr(claude, "get_client", lambda: fake)

    async def collect():
        history = [{"role": "user", "content": "hi"}]
        return [e async for e in claude.claude_reply(history, LANGUAGES["fr"])]

    asyncio.run(collect())
    assert "Reply only in French." in fake.calls[0]["system"]


def test_chosen_language_changes_the_search_filler(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "settings", "language": "es"})
        ws.send_json({"type": "user_text", "text": "what is the weather"})
        messages = read_until(ws, "done")
    sentences = [m["text"] for m in messages if m["type"] == "sentence"]
    assert sentences[0] == LANGUAGES["es"].filler


def test_unknown_language_gets_a_friendly_error_and_changes_nothing(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "settings", "language": "klingon"})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "user_text", "text": "latest news"})
        messages = read_until(ws, "done")
    assert LANGUAGES["en"].filler in [m.get("text") for m in messages]


def test_deepgram_listens_in_the_chosen_language(client, voice_keys, monkeypatch):  # noqa: F811
    assert "language=en" in stt.deepgram_url(16000)
    seen = {}

    async def fake_connect(url, additional_headers):
        seen["url"] = url
        return FakeDeepgram()

    monkeypatch.setattr(stt, "connect", fake_connect)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "settings", "language": "tw"})
        ws.send_json({"type": "audio_start", "sample_rate": 16000})
        ws.send_json({"type": "user_text", "text": "hi"})  # proves audio_start was handled
        read_until(ws, "done")
    assert "language=ak" in seen["url"]  # Deepgram calls Twi "Akan"


# ---------- voices ----------

def test_voices_come_from_the_settings(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "id-main")
    monkeypatch.setattr(settings, "elevenlabs_voices", "Ama:id-ama, Tunde : id-tunde, broken")
    assert settings.voices == {"Default": "id-main", "Ama": "id-ama", "Tunde": "id-tunde"}
    assert settings.voice_id("Tunde") == "id-tunde"
    assert settings.voice_id("nobody") == "id-main"


def test_extra_voices_alone_are_enough_for_elevenlabs(monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "el-test")
    monkeypatch.setattr(settings, "elevenlabs_voices", "Ama:id-ama")
    assert settings.tts_mode == "elevenlabs" and settings.voice_id("") == "id-ama"


def test_ready_lists_voice_names_but_never_their_ids(client, voice_keys, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "elevenlabs_voices", "Ama:id-ama")
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert ready["voices"] == ["Default", "Ama"]
    assert "id-ama" not in json.dumps(ready) and "voice-test" not in json.dumps(ready)


def test_chosen_voice_speaks_the_reply(client, voice_keys, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "elevenlabs_voices", "Ama:id-ama")

    async def fake(http, text, voice_id):
        return voice_id.encode()

    monkeypatch.setattr(tts, "synthesize", fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        for voice, expected in (("Ama", "id-ama"), ("someone else", "voice-test")):
            ws.send_json({"type": "settings", "language": "en", "voice": voice})
            ws.send_json({"type": "user_text", "text": "hello"})
            audio = [m["audio"] for m in read_until(ws, "done") if m["type"] == "audio"]
            assert audio and all(base64.b64decode(a).decode() == expected for a in audio)

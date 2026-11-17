"""The Abena voice choices. All faked, no keys."""
import base64
import json

from app import abena
from app.abena_voices import voice_id
from app.config import settings
from tests.conftest import read_until


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

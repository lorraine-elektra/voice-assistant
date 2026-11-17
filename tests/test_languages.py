"""The language and voice choices. No keys, no network."""
from app.languages import LANGUAGES
from app.prompts import system_prompt
from tests.conftest import read_until


def test_ready_lists_the_languages(client):
    with client.websocket_connect("/ws") as ws:
        ready = ws.receive_json()
    assert [lang["name"] for lang in ready["languages"]] == [
        "Detect automatically", "English", "Spanish", "French", "Naija Pidgin", "Ghana Pidgin", "Ghana Twi",
    ]
    assert all(lang["id"] and lang["browser"] for lang in ready["languages"])


def test_every_language_tells_gemini_what_to_speak():
    for language in LANGUAGES.values():
        assert language.instruction in system_prompt(language)
    assert "Nigerian Pidgin" in system_prompt(LANGUAGES["pcm-NG"])
    assert "Twi" in system_prompt(LANGUAGES["tw"])


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

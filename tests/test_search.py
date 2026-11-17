"""The web lookup flow, tested with the mock over the WebSocket."""
import time

from app.config import settings
from app.languages import DEFAULT
from tests.conftest import read_until


def ask(client, text):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": text})
        return read_until(ws, "done")


def test_lookup_question_searches_and_shows_sources(client):
    messages = ask(client, "What is the weather today?")
    kinds = [(m["type"], m.get("state")) for m in messages]
    searching = kinds.index(("status", "searching"))
    assert messages[searching + 1]["text"] == DEFAULT.filler  # no long silence
    assert ("status", "thinking") in kinds[searching:]
    sources = next(m for m in messages if m["type"] == "sources")["sources"]
    assert sources[0]["url"].startswith("https://")
    spoken = " ".join(m["text"] for m in messages if m["type"] == "sentence")
    assert "According to Example News" in spoken  # names the source
    assert "http" not in spoken  # never reads out a URL


def test_small_talk_does_not_search(client):
    messages = ask(client, "Hello, how are you?")
    assert not [m for m in messages if m.get("state") == "searching"]
    assert not [m for m in messages if m["type"] == "sources"]


def test_failed_search_says_so_and_still_answers(client):
    messages = ask(client, "Search for the unreachable thing")
    assert {"type": "search_failed", "turn": 1} in messages
    spoken = " ".join(m["text"] for m in messages if m["type"] == "sentence")
    assert "could not look that up" in spoken
    assert "From what I already know" in spoken
    assert messages[-1]["type"] == "done"


def test_barge_in_cancels_a_search_in_progress(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_search_delay", 30)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "latest news please"})
        read_until(ws, "sentence")  # the filler: the search is now running
        started = time.monotonic()
        ws.send_json({"type": "stop"})
        assert read_until(ws, "cancelled")[-1]["turn"] == 1
        assert time.monotonic() - started < 5
        ws.send_json({"type": "user_text", "text": "hi"})
        assert all(m["turn"] == 2 for m in read_until(ws, "done"))

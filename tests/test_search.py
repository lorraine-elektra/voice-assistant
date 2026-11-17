"""Web lookup, tested two ways: the mock over the WebSocket, and a fake Claude stream."""
import asyncio
import time
from types import SimpleNamespace as NS

from app import claude
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


# ---- a fake Claude, so the real code path is tested with no key ----

def start(block):
    return NS(type="content_block_start", content_block=block)


def text(value):
    return NS(type="content_block_delta", delta=NS(type="text_delta", text=value))


def cite(url, title):
    citation = NS(url=url, title=title)
    return NS(type="content_block_delta", delta=NS(type="citations_delta", citation=citation))


SEARCH = start(NS(type="server_tool_use", name="web_search"))
RESULTS = start(NS(type="web_search_tool_result", content=[NS(url="https://a.example")]))
FAILED = start(NS(type="web_search_tool_result", content=NS(error_code="unavailable")))


class FakeStream:
    def __init__(self, events, stop_reason):
        self.events, self.stop_reason = events, stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def __aiter__(self):
        for event in self.events:
            yield event

    async def get_final_message(self):
        return NS(stop_reason=self.stop_reason, content=["paused content"])


class FakeClient:
    def __init__(self, *streams):
        self.streams = list(streams)
        self.calls = []
        self.messages = NS(stream=self.stream)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return self.streams.pop(0)


def run_claude(monkeypatch, *streams):
    fake = FakeClient(*streams)
    monkeypatch.setattr(claude, "get_client", lambda: fake)

    async def collect():
        return [e async for e in claude.claude_reply([{"role": "user", "content": "hi"}])]

    return asyncio.run(collect()), fake


def test_claude_search_becomes_events_and_cited_sources(monkeypatch):
    stream = FakeStream(
        [SEARCH, RESULTS, text("It is sunny, "), cite("https://a.example", "A"),
         cite("https://a.example", "A"), text("says A.")],
        "end_turn",
    )
    events, fake = run_claude(monkeypatch, stream)
    assert [e["type"] for e in events] == ["searching", "search_done", "text", "text", "sources"]
    assert events[-1]["sources"] == [{"title": "A", "url": "https://a.example"}]


def test_claude_search_limit_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "web_search_max_uses", 1)
    _, fake = run_claude(monkeypatch, FakeStream([text("Hi.")], "end_turn"))
    assert fake.calls[0]["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 1}
    ]


def test_claude_failed_search_is_reported(monkeypatch):
    stream = FakeStream([SEARCH, FAILED, text("I could not look it up.")], "end_turn")
    events, _ = run_claude(monkeypatch, stream)
    assert events[1] == {"type": "search_failed", "reason": "unavailable"}
    assert events[-1]["type"] == "text"


def test_claude_plain_answer_has_no_search_events(monkeypatch):
    events, _ = run_claude(monkeypatch, FakeStream([text("Hello!")], "end_turn"))
    assert events == [{"type": "text", "text": "Hello!"}]


def test_claude_paused_search_is_resumed(monkeypatch):
    first = FakeStream([SEARCH], "pause_turn")
    second = FakeStream([RESULTS, text("Done.")], "end_turn")
    events, fake = run_claude(monkeypatch, first, second)
    assert events[-1] == {"type": "text", "text": "Done."}
    assert fake.calls[1]["messages"][-1] == {"role": "assistant", "content": ["paused content"]}


def test_claude_refusal_gets_a_spoken_line(monkeypatch):
    events, _ = run_claude(monkeypatch, FakeStream([], "refusal"))
    assert events == [{"type": "text", "text": claude.REFUSAL_TEXT}]

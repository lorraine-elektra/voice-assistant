import asyncio

from app.config import settings
from app.mock import mock_reply
from tests.conftest import read_until


def test_mock_reply_streams_text_with_no_keys():
    async def collect():
        return [e async for e in mock_reply([{"role": "user", "content": "hi"}])]

    events = asyncio.run(collect())
    assert len(events) > 3
    assert all(e["type"] == "text" for e in events)
    assert "mock reply" in "".join(e["text"] for e in events)


def test_ready_message_says_mock(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["brain"] == "mock"


def test_text_in_sentences_out(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    assert messages[0] == {"type": "status", "turn": 1, "state": "thinking"}
    sentences = [m for m in messages if m["type"] == "sentence"]
    assert [s["index"] for s in sentences] == [0, 1, 2]
    assert sentences[1]["text"] == "You said: hello."
    assert messages[-1] == {"type": "done", "turn": 1}


def test_turn_numbers_go_up(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        for expected_turn in (1, 2):
            ws.send_json({"type": "user_text", "text": "again"})
            assert read_until(ws, "done")[-1]["turn"] == expected_turn


def test_bad_messages_get_a_friendly_error(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        for bad in ("not json", '{"type": "user_text", "text": "  "}', '{"type": "dance"}'):
            ws.send_text(bad)
            assert ws.receive_json()["type"] == "error"


def test_new_message_cancels_the_reply_in_progress(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_word_delay", 0.05)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "first"})
        read_until(ws, "sentence")  # the first reply has started
        ws.send_json({"type": "user_text", "text": "second"})
        messages = read_until(ws, "done")
    cancelled_at = messages.index({"type": "cancelled", "turn": 1})
    after = messages[cancelled_at + 1:]
    assert after and all(m["turn"] == 2 for m in after)
    assert any("second" in m.get("text", "") for m in after)


def test_stop_cancels_and_nothing_else_arrives(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_word_delay", 0.05)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "first"})
        read_until(ws, "sentence")
        ws.send_json({"type": "stop"})
        assert read_until(ws, "cancelled")[-1] == {"type": "cancelled", "turn": 1}
        # Anything from the old reply would arrive before this next turn's messages.
        ws.send_json({"type": "user_text", "text": "next"})
        assert all(m["turn"] == 2 for m in read_until(ws, "done"))


def test_stop_with_nothing_running_is_harmless(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "stop"})
        ws.send_json({"type": "user_text", "text": "hi"})
        assert read_until(ws, "done")[0]["type"] == "status"


def test_a_question_stopped_before_any_answer_is_forgotten(client, monkeypatch):
    seen = []

    async def fake(history, language, name=""):
        seen.append([turn["content"] for turn in history])
        if history[-1]["content"] == "first":
            await asyncio.sleep(30)  # still thinking when the user presses Stop
        yield {"type": "text", "text": "Fine."}

    monkeypatch.setattr("app.session.reply_events", fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "first"})
        read_until(ws, "status")
        ws.send_json({"type": "stop"})
        read_until(ws, "cancelled")
        ws.send_json({"type": "user_text", "text": "second"})
        read_until(ws, "done")
        ws.send_json({"type": "user_text", "text": "third"})
        read_until(ws, "done")
    assert seen[-2:] == [["second"], ["second", "Fine.", "third"]]

"""Regression check: whole conversations from conversations.json, run in mock mode.

Each turn says what the user says and what must come back. Add a conversation to
the JSON file whenever a bug is fixed, so it cannot quietly return.
"""
import json
from pathlib import Path

import pytest

from tests.conftest import read_until

CONVERSATIONS = json.loads((Path(__file__).parent / "conversations.json").read_text())
FORBIDDEN = ("http", "*", "#", "`")  # never spoken: URLs and markdown


@pytest.mark.parametrize("conversation", CONVERSATIONS, ids=lambda c: c["name"])
def test_conversation(client, conversation):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        for number, turn in enumerate(conversation["turns"], start=1):
            ws.send_json({"type": "user_text", "text": turn["say"]})
            messages = read_until(ws, "done", "error")

            assert messages[-1] == {"type": "done", "turn": number}
            assert all(m["turn"] == number for m in messages)
            sentences = [m for m in messages if m["type"] == "sentence"]
            assert [s["index"] for s in sentences] == list(range(len(sentences)))
            spoken = " ".join(s["text"] for s in sentences)
            for expected in turn["hear"]:
                assert expected in spoken
            assert not any(bad in spoken for bad in FORBIDDEN)

            searched = any(m.get("state") == "searching" for m in messages)
            assert searched == turn["search"]
            assert any(m["type"] == "sources" for m in messages) == turn.get("sources", False)
            assert any(m["type"] == "search_failed" for m in messages) == turn.get("failed", False)

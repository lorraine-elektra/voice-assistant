"""Gemini, faked. No keys, no network."""
import asyncio
import json

import httpx

from app import gemini
from app.config import settings
from app.languages import LANGUAGES
from app.prompts import system_prompt
from tests.conftest import read_until


def sse(*texts):
    """A fake streamGenerateContent body: one event per piece of the JSON text."""
    events = [{"candidates": [{"content": {"parts": [{"text": t}]}}]} for t in texts]
    return "".join(f"data: {json.dumps(e)}\r\n\r\n" for e in events).encode()


def run_gemini(monkeypatch, body, language=None, status=200):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), key=request.headers["x-goog-api-key"], body=json.loads(request.content))
        return httpx.Response(status, content=body)

    monkeypatch.setattr(settings, "gemini_api_key", "gm-test")
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")  # not whatever .env says
    monkeypatch.setattr(gemini, "get_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def collect():
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello."}]
        return [e async for e in gemini.gemini_reply(history, language or LANGUAGES["auto"])]

    return asyncio.run(collect()), seen


def test_reply_streams_text_and_reports_the_language(monkeypatch):
    body = sse('{"detected_language": "pcm-GH", ', '"reply_text": "Chale, I dey', ' fine! How I fit help?"}')
    events, seen = run_gemini(monkeypatch, body)
    assert events[0] == {"type": "language", "language": "pcm-GH"}
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Chale, I dey fine! How I fit help?"
    assert seen["key"] == "gm-test" and "gm-test" not in seen["url"]
    assert seen["url"].endswith("gemini-2.5-flash:streamGenerateContent?alt=sse")


def test_request_carries_history_schema_and_language_rules(monkeypatch):
    _, seen = run_gemini(monkeypatch, sse('{"detected_language": "en", "reply_text": "Hi."}'))
    body = seen["body"]
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"]["properties"]["detected_language"]["enum"] == list(LANGUAGES)
    assert system_prompt(LANGUAGES["auto"]) in body["systemInstruction"]["parts"][0]["text"]


def test_the_assistants_name_goes_into_the_prompt():
    assert "named you Ama" in system_prompt(LANGUAGES["auto"], "Ama")
    assert "named you" not in system_prompt(LANGUAGES["auto"])


def test_name_from_settings_reaches_the_brain(client, monkeypatch):
    seen = {}

    async def fake(history, language, name=""):
        seen["name"] = name
        yield {"type": "text", "text": "Hi."}

    monkeypatch.setattr("app.session.reply_events", fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "settings", "language": "en", "voice": "", "name": "  Ama   Mensah " + "x" * 50})
        ws.send_json({"type": "user_text", "text": "hello"})
        read_until(ws, "done")
    assert seen["name"].startswith("Ama Mensah x") and len(seen["name"]) == 30


def test_escapes_split_across_chunks_are_decoded(monkeypatch):
    body = sse('{"detected_language": "fr", "reply_text": "Il dit \\"all', 'o\\" \u00e9t', '\u00e9."}')
    events, _ = run_gemini(monkeypatch, body)
    assert "".join(e["text"] for e in events if e["type"] == "text") == 'Il dit "allo" été.'


def test_unknown_language_is_not_reported(monkeypatch):
    events, _ = run_gemini(monkeypatch, sse('{"detected_language": "klingon", "reply_text": "Qapla."}'))
    assert [e["type"] for e in events] == ["text"]


def test_empty_answer_gets_a_spoken_line(monkeypatch):
    events, _ = run_gemini(monkeypatch, b'data: {"promptFeedback": {"blockReason": "SAFETY"}}\r\n\r\n')
    assert events == [{"type": "text", "text": gemini.REFUSAL_TEXT}]


def test_http_error_is_raised(monkeypatch):
    try:
        run_gemini(monkeypatch, b"{}", status=429)
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected an error")


def test_real_gemini_mode_needs_a_key(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["brain"] == "mock"
    monkeypatch.setattr(settings, "gemini_api_key", "gm-test")
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["brain"] == "gemini"


def test_detected_language_reaches_the_browser(client, monkeypatch):
    async def fake(history, language):
        yield {"type": "language", "language": "tw"}
        yield {"type": "text", "text": "Ɛte sɛn?"}

    monkeypatch.setattr("app.session.reply_events", fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        messages = read_until(ws, "done")
    assert {"type": "language", "turn": 1, "language": "tw"} in messages


def test_emoji_written_as_an_escaped_pair_is_decoded(monkeypatch):
    body = sse('{"detected_language": "en", "reply_text": "Hi \\ud83d', '\\ude00 there."}')
    events, _ = run_gemini(monkeypatch, body)
    assert "".join(e["text"] for e in events if e["type"] == "text") == "Hi \U0001F600 there."


def test_a_stalled_request_is_tried_once_more(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("stalled")
        return httpx.Response(200, content=sse('{"detected_language": "en", "reply_text": "Hi."}'))

    monkeypatch.setattr(settings, "gemini_api_key", "gm-test")
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")
    monkeypatch.setattr(gemini, "get_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def collect():
        return [e async for e in gemini.gemini_reply([{"role": "user", "content": "hi"}])]

    assert asyncio.run(collect())[-1] == {"type": "text", "text": "Hi."}
    assert len(calls) == 2


def failing_reply(client, monkeypatch, error):
    async def fake(history, language, name=""):
        raise error
        yield

    monkeypatch.setattr("app.session.reply_events", fake)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_text", "text": "hello"})
        return read_until(ws, "error")[-1]


def test_the_free_limit_and_a_timeout_get_their_own_messages(client, monkeypatch):
    request = httpx.Request("POST", gemini.API)
    limit = httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))
    assert "limit" in failing_reply(client, monkeypatch, limit)["message"]
    assert "too long" in failing_reply(client, monkeypatch, httpx.ReadTimeout("stalled"))["message"]
    other = failing_reply(client, monkeypatch, RuntimeError("secret detail"))
    assert other["turn"] == 1 and "secret" not in other["message"]


def test_real_gemini_mode_needs_a_model_too(client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", False)
    monkeypatch.setattr(settings, "gemini_api_key", "gm-test")
    monkeypatch.setattr(settings, "gemini_model", "")
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["brain"] == "mock"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """Every test runs with no keys, whatever is in the developer's .env."""
    monkeypatch.setattr(settings, "mock_mode", True)
    for key in ("anthropic_api_key", "deepgram_api_key", "elevenlabs_api_key", "elevenlabs_voice_id"):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "mock_word_delay", 0)
    monkeypatch.setattr(settings, "mock_search_delay", 0)


@pytest.fixture
def client():
    return TestClient(app)


def read_until(ws, *types):
    """Collect messages until one of the given types arrives."""
    messages = []
    while True:
        messages.append(ws.receive_json())
        if messages[-1]["type"] in types:
            return messages

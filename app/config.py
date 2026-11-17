"""All settings come from the environment (.env). Nothing is hard coded elsewhere."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    mock_mode: bool
    anthropic_api_key: str
    anthropic_model: str
    anthropic_effort: str
    web_search_max_uses: int
    deepgram_api_key: str
    deepgram_model: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    # Mock timing, so the mock feels like a real stream. Tests change these.
    mock_word_delay: float = 0.04
    mock_search_delay: float = 1.5

    @property
    def brain_mode(self) -> str:
        """'claude' when we can really call Claude, otherwise 'mock'."""
        return "claude" if not self.mock_mode and self.anthropic_api_key else "mock"

    @property
    def stt_mode(self) -> str:
        """Speech to text: 'deepgram' with a key, otherwise the browser does it."""
        return "deepgram" if not self.mock_mode and self.deepgram_api_key else "browser"

    @property
    def tts_mode(self) -> str:
        """Text to speech: 'elevenlabs' with a key and a voice, otherwise the browser."""
        ready = self.elevenlabs_api_key and self.elevenlabs_voice_id
        return "elevenlabs" if not self.mock_mode and ready else "browser"


def load_settings() -> Settings:
    return Settings(
        mock_mode=_env("MOCK_MODE", "true").lower() in ("1", "true", "yes"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        anthropic_effort=_env("ANTHROPIC_EFFORT", "low"),
        web_search_max_uses=int(_env("WEB_SEARCH_MAX_USES", "2")),
        deepgram_api_key=_env("DEEPGRAM_API_KEY"),
        deepgram_model=_env("DEEPGRAM_MODEL", "nova-3"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID"),
        elevenlabs_model=_env("ELEVENLABS_MODEL"),
    )


settings = load_settings()

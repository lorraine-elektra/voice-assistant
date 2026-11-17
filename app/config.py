"""All settings come from the environment (.env). Nothing is hard coded elsewhere."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app import abena_voices

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    mock_mode: bool
    gemini_api_key: str
    gemini_model: str
    abena_api_key: str
    # Mock timing, so the mock feels like a real stream. Tests change these.
    mock_word_delay: float = 0.04
    mock_search_delay: float = 1.5

    @property
    def brain_mode(self) -> str:
        """'gemini' when we can really call Gemini (key and model both set), otherwise 'mock'."""
        ready = not self.mock_mode and self.gemini_api_key and self.gemini_model
        return "gemini" if ready else "mock"

    @property
    def tts_mode(self) -> str:
        """Text to speech: 'abena' speaks Twi and Pidgin when it has a key. The browser speaks
        everything else, and everything when there is no key."""
        return "abena" if self.abena_mode else "browser"

    @property
    def abena_mode(self) -> bool:
        """Abena speaks, and listens for, Twi and Pidgin whenever we are not in mock mode. Its playground API
        works without a key, so ABENA_API_KEY is optional and only sent when set."""
        return not self.mock_mode

    def abena_voice(self, language_id: str, choice: str = "") -> str:
        """The Abena voice for a language and the voice picked on the page ("" if none)."""
        return abena_voices.voice_id(language_id, choice) if self.abena_mode else ""


def load_settings() -> Settings:
    return Settings(
        mock_mode=_env("MOCK_MODE", "true").lower() in ("1", "true", "yes"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL"),
        abena_api_key=_env("ABENA_API_KEY"),
    )


settings = load_settings()

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
    groq_api_key: str
    groq_model: str
    abena_api_key: str
    # Mock timing, so the mock feels like a real stream. Tests change these.
    mock_word_delay: float = 0.04
    mock_search_delay: float = 1.5

    @property
    def brain_mode(self) -> str:
        """'gemini' when we can really call Gemini, otherwise 'mock'."""
        return "gemini" if not self.mock_mode and self.gemini_api_key else "mock"

    @property
    def stt_mode(self) -> str:
        """Speech to text: 'whisper' (Groq) with a key, otherwise the browser does it."""
        return "whisper" if not self.mock_mode and self.groq_api_key else "browser"

    @property
    def tts_mode(self) -> str:
        """Text to speech: 'abena' speaks Twi and Pidgin when it has a key. The browser speaks
        everything else, and everything when there is no key."""
        return "abena" if self.abena_mode else "browser"

    @property
    def abena_mode(self) -> bool:
        """Abena speaks Twi and Pidgin when we have its key."""
        return not self.mock_mode and bool(self.abena_api_key)

    def abena_voice(self, language_id: str, choice: str = "") -> str:
        """The Abena voice for a language and the voice picked on the page ("" if none)."""
        return abena_voices.voice_id(language_id, choice) if self.abena_mode else ""


def load_settings() -> Settings:
    return Settings(
        mock_mode=_env("MOCK_MODE", "true").lower() in ("1", "true", "yes"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_api_key=_env("GROQ_API_KEY"),
        groq_model=_env("GROQ_MODEL", "whisper-large-v3"),
        abena_api_key=_env("ABENA_API_KEY"),
    )


settings = load_settings()

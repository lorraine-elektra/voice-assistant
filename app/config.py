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
    # Mock timing, so the mock feels like a real stream. Tests change these.
    mock_word_delay: float = 0.04
    mock_search_delay: float = 1.5

    @property
    def brain_mode(self) -> str:
        """'claude' when we can really call Claude, otherwise 'mock'."""
        return "claude" if not self.mock_mode and self.anthropic_api_key else "mock"


def load_settings() -> Settings:
    return Settings(
        mock_mode=_env("MOCK_MODE", "true").lower() in ("1", "true", "yes"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        anthropic_effort=_env("ANTHROPIC_EFFORT", "low"),
        web_search_max_uses=int(_env("WEB_SEARCH_MAX_USES", "2")),
    )


settings = load_settings()

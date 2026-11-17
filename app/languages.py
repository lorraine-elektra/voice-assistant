"""The languages the assistant can use. One row per language, nothing else decides it.

Checked against the Deepgram and ElevenLabs docs in November 2026:
* Deepgram Nova-3 listens in English, Spanish, French and Akan (Twi). It has no Pidgin,
  so Pidgin is heard with the English recogniser.
* ElevenLabs has no Pidgin or Twi voice. It reads the text with whichever voice is chosen.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    id: str           # what the browser sends in the `settings` message
    name: str         # shown in the language picker
    instruction: str  # added to Claude's system prompt
    deepgram: str     # Deepgram `language` code
    browser: str      # tag for the browser's speech recognition and voices
    filler: str       # spoken while a web search runs


_ALL = [
    Language("en", "English", "Reply in English.", "en", "en-US", "Let me look that up."),
    Language("es", "Spanish", "Reply only in Spanish.", "es", "es-ES", "Déjame buscarlo."),
    Language("fr", "French", "Reply only in French.", "fr", "fr-FR", "Laissez-moi vérifier."),
    Language(
        "pcm-NG", "Naija Pidgin",
        "Reply only in Nigerian Pidgin (Naija), the way people speak it every day in "
        "Nigeria. Spell it with ordinary English letters.",
        "en", "en-NG", "Make I check am.",
    ),
    Language(
        "pcm-GH", "Ghana Pidgin",
        "Reply only in Ghanaian Pidgin English, the way people speak it every day in "
        "Ghana. Spell it with ordinary English letters.",
        "en", "en-GH", "Make I check am.",
    ),
    Language(
        "tw", "Ghana Twi", "Reply only in Twi (Akan), as spoken in Ghana.",
        "ak", "ak-GH", "Ma me nhwɛ.",
    ),
]

LANGUAGES = {language.id: language for language in _ALL}
DEFAULT = LANGUAGES["en"]


def for_browser() -> list[dict]:
    """What the page needs to build its picker."""
    return [{"id": lang.id, "name": lang.name, "browser": lang.browser} for lang in _ALL]

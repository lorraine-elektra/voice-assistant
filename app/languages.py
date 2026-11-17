"""The languages the assistant can use. One row per language, nothing else decides it.

Gemini replies in the language it detects or the one picked on the page. Whisper (Groq)
detects what was said by itself. Abena speaks Twi and both Pidgins, the browser the rest.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    id: str           # what the browser sends in the `settings` message
    name: str         # shown in the language picker
    instruction: str  # added to Gemini's system prompt
    browser: str      # tag for the browser's speech recognition and voices
    filler: str       # spoken while a web search runs


_ALL = [
    Language(
        "auto", "Detect automatically",
        "Work out which language the listener used and reply in that same language. Hints: "
        "'how far' or 'wetin' means Naija Pidgin, 'chale' or 'dey go' means Ghana Pidgin, "
        "'ɛte sɛn' or 'medaase' means Twi. Spell Pidgin and Twi with the letters people "
        "normally use for them.",
        "en-US", "Let me look that up.",
    ),
    Language("en", "English", "Reply in English.", "en-US", "Let me look that up."),
    Language("es", "Spanish", "Reply only in Spanish.", "es-ES", "Déjame buscarlo."),
    Language("fr", "French", "Reply only in French.", "fr-FR", "Laissez-moi vérifier."),
    Language(
        "pcm-NG", "Naija Pidgin",
        "Reply only in Nigerian Pidgin (Naija), the way people speak it every day in "
        "Nigeria. Spell it with ordinary English letters.",
        "en-NG", "Make I check am.",
    ),
    Language(
        "pcm-GH", "Ghana Pidgin",
        "Reply only in Ghanaian Pidgin English, the way people speak it every day in "
        "Ghana. Spell it with ordinary English letters.",
        "en-GH", "Make I check am.",
    ),
    Language(
        "tw", "Ghana Twi", "Reply only in Twi (Akan), as spoken in Ghana.",
        "ak-GH", "Ma me nhwɛ.",
    ),
]

LANGUAGES = {language.id: language for language in _ALL}
DEFAULT = LANGUAGES["auto"]


def for_browser() -> list[dict]:
    """What the page needs to build its picker."""
    return [{"id": lang.id, "name": lang.name, "browser": lang.browser} for lang in _ALL]

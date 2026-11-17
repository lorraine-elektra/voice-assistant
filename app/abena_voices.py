"""The Abena voices offered on the page, per language. The first in each list is the default.

Checked against https://abena.mobobi.com/playground/api/v1/tts/voices.json in November 2026.
Abena has only one Twi man (Kofi) and no Pidgin woman. For Pidgin, the woman is one of its
English voices (Ghanaian or Nigerian accent) reading the Pidgin text, and Kwabena is the
same kind of voice for a second Ghanaian man. The note says so on the page.
"""

# (name shown, gender, Abena voice id, note shown)
VOICES = {
    "tw": [
        ("Abena", "woman", "abena_twi_medium", ""),
        ("Ama", "woman", "ama_twi_medium", ""),
        ("Yaa", "woman", "yaa_twi_medium", ""),
        ("Kofi", "man", "kofi_twi_medium", ""),
    ],
    "pcm-GH": [
        ("Kobby", "man", "kobby_gpe_medium", ""),
        ("Kwabena", "man", "kwabena_eng_medium", "Ghanaian English accent"),
        ("Akua", "woman", "akua_eng_medium", "Ghanaian English accent"),
    ],
    "pcm-NG": [
        ("James", "man", "james_pcm_medium", ""),
        ("Chioma", "woman", "chioma_eng", "Nigerian English accent"),
    ],
}


def for_browser() -> dict:
    """What the page needs for its voice picker. Names only, never the Abena ids."""
    return {
        language: [{"name": name, "gender": gender, "note": note} for name, gender, _, note in voices]
        for language, voices in VOICES.items()
    }


def voice_id(language_id: str, choice: str = "") -> str:
    """The Abena voice id for a language, or "" if Abena does not speak it.
    `choice` is a voice name, or "woman" or "man". Anything else gets the default."""
    voices = VOICES.get(language_id)
    if not voices:
        return ""
    wanted = choice.strip().lower()
    for name, gender, voice, _ in voices:
        if wanted in (name.lower(), gender):
            return voice
    return voices[0][2]

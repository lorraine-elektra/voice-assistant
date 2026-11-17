// The language and voice pickers. The choices are remembered in this browser.
// The list of languages, and of ElevenLabs voices, comes from the backend's `ready` message.
const canSpeak = "speechSynthesis" in window;
const FALLBACK = { id: "en", name: "English", browser: "en-US" };

function recall(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function remember(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private window: just not remembered */ }
}

const primary = (tag) => tag.toLowerCase().split("-")[0];

export class Choices {
  // languageEl and voiceEl are <select> elements. onChange runs after the user picks.
  constructor({ languageEl, voiceEl, onChange }) {
    this.els = { language: languageEl, voice: voiceEl };
    this.languages = [FALLBACK];
    this.serverVoices = [];  // ElevenLabs voice names. Empty means the browser speaks.
    languageEl.addEventListener("change", () => {
      remember("language", languageEl.value);
      this.fillVoices();
      onChange();
    });
    voiceEl.addEventListener("change", () => {
      remember(this.voiceKey, voiceEl.value);
      onChange();
    });
    // Browsers load their voices late, so fill the list again when they arrive.
    if (canSpeak) speechSynthesis.addEventListener?.("voiceschanged", () => { this.fillVoices(); onChange(); });
    this.fillLanguages();
  }

  // Called with the backend's `ready` message.
  setOptions({ languages, voices }) {
    if (languages?.length) this.languages = languages;
    this.serverVoices = voices || [];
    this.fillLanguages();
  }

  get language() {
    return this.languages.find((lang) => lang.id === this.els.language.value) || this.languages[0];
  }

  // The tag for the browser's speech recognition and voices. For English, Spanish and
  // French the user's own region wins (en-GB stays en-GB). Pidgin and Twi are fixed.
  get tag() {
    const lang = this.language;
    const mine = navigator.language || "";
    return primary(mine) === lang.id ? mine : lang.browser;
  }

  // The browser voice to speak with, or null for the browser's default.
  get browserVoice() {
    if (!canSpeak) return null;
    const name = this.serverVoices.length ? recall(`voice:${this.language.id}`) : this.els.voice.value;
    return speechSynthesis.getVoices().find((voice) => voice.name === name) || null;
  }

  // What the backend needs to know.
  get message() {
    const voice = this.serverVoices.length ? this.els.voice.value : "";
    return { type: "settings", language: this.language.id, voice };
  }

  get voiceKey() {
    return this.serverVoices.length ? "voice:elevenlabs" : `voice:${this.language.id}`;
  }

  fillLanguages() {
    const wanted = recall("language") || this.els.language.value;
    this.els.language.replaceChildren(...this.languages.map((lang) => new Option(lang.name, lang.id)));
    if (this.languages.some((lang) => lang.id === wanted)) this.els.language.value = wanted;
    this.fillVoices();
  }

  fillVoices() {
    const options = this.serverVoices.length
      ? this.serverVoices.map((name) => new Option(name, name))
      : [new Option("Browser default", ""), ...this.matchingBrowserVoices().map((v) => new Option(`${v.name} (${v.lang})`, v.name))];
    this.els.voice.replaceChildren(...options);
    const wanted = recall(this.voiceKey);
    if (options.some((option) => option.value === wanted)) this.els.voice.value = wanted;
    this.els.voice.disabled = options.length < 2;
  }

  // Browser voices for the chosen language, the exact region first (en-NG before en-US).
  // A language with no voice at all (Twi on most machines) gets every voice to pick from.
  matchingBrowserVoices() {
    if (!canSpeak) return [];
    const all = speechSynthesis.getVoices();
    const tag = this.language.browser.toLowerCase();
    const same = all.filter((voice) => primary(voice.lang.replace("_", "-")) === primary(tag));
    const exact = (voice) => voice.lang.replace("_", "-").toLowerCase() === tag;
    return (same.length ? same : all).sort((a, b) => exact(b) - exact(a));
  }
}

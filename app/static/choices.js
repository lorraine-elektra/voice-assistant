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

// Browsers do not say whether a voice is a woman's or a man's, so we go by the voice's name.
const WOMEN = /\b(female|woman|zira|aria|jenny|hazel|susan|linda|heidi|helena|laura|sabina|hortense|julie|denise|elvira|paulina|monica|samantha|victoria|karen|moira|tessa|fiona|amelie|marie|sonia|libby|mia|emma|catherine|nancy)\b/i;
const MEN = /\b(male|man|david|mark|george|james|richard|guy|ryan|pablo|raul|paul|claude|henri|alvaro|jorge|antoine|mathieu|daniel|thomas|alex|diego|juan|tom|oliver|liam)\b/i;

export function genderOf(name) {
  if (WOMEN.test(name)) return "woman";
  return MEN.test(name) ? "man" : null;
}

export class Choices {
  // languageEl and voiceEl are <select> elements, genderEls the "woman" and "man" radio buttons.
  // onChange runs after the user picks. helpEl gets a line saying what the voice list holds.
  constructor({ languageEl, voiceEl, genderEls, helpEl, onChange }) {
    this.els = { language: languageEl, voice: voiceEl, help: helpEl };
    this.genderEls = [...genderEls];
    this.languages = [FALLBACK];
    this.serverVoices = [];  // ElevenLabs voice names. Empty means the browser speaks.
    this.abenaVoices = {};   // language id -> Abena voices, for Twi and Pidgin
    const saved = recall("gender");
    this.genderEls.forEach((radio) => {
      radio.checked = radio.value === (saved || "woman");
      radio.addEventListener("change", () => {
        remember("gender", this.gender);
        this.fillVoices();
        onChange();
      });
    });
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
  setOptions({ languages, voices, abena_voices }) {
    if (languages?.length) this.languages = languages;
    this.serverVoices = voices || [];
    this.abenaVoices = abena_voices || {};
    this.fillLanguages();
  }

  // "woman" or "man", from the radio buttons.
  get gender() {
    return this.genderEls.find((radio) => radio.checked)?.value || "woman";
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
    const name = this.sendsVoice ? recall(`voice:${this.language.id}`) : this.els.voice.value;
    return speechSynthesis.getVoices().find((voice) => voice.name === name) || null;
  }

  // What the backend needs to know.
  get message() {
    const voice = this.sendsVoice ? this.els.voice.value : "";
    return { type: "settings", language: this.language.id, voice };
  }

  // True when the backend, not the browser, needs to know which voice was picked.
  get sendsVoice() {
    return Boolean(this.abenaVoices[this.language.id]) || this.serverVoices.length > 0 || this.language.id === "auto";
  }

  get voiceKey() {
    if (this.abenaVoices[this.language.id]) return `voice:abena:${this.language.id}`;
    return this.serverVoices.length ? "voice:elevenlabs" : `voice:${this.language.id}`;
  }

  // In automatic mode the reply language is only known once Gemini says it. This finds the
  // browser voice of the picked kind (woman or man) for that language.
  voiceFor(languageId) {
    if (this.language.id !== "auto" || !canSpeak) return null;
    const lang = this.languages.find((item) => item.id === languageId);
    if (!lang) return null;
    const mine = navigator.language || "";
    const tag = primary(mine) === lang.id ? mine : lang.browser;
    const kind = this.gender;
    const voice = speechSynthesis.getVoices()
      .filter((item) => primary(item.lang.replace("_", "-")) === primary(tag))
      .find((item) => genderOf(item.name) === kind);
    return { tag, voice: voice || null };
  }

  fillLanguages() {
    const wanted = recall("language") || this.els.language.value;
    this.els.language.replaceChildren(...this.languages.map((lang) => new Option(lang.name, lang.id)));
    if (this.languages.some((lang) => lang.id === wanted)) this.els.language.value = wanted;
    this.fillVoices();
  }

  // Lists only the voices of the picked gender. If we cannot tell (ElevenLabs gives names only,
  // some browsers give odd names), everything is listed and the help line says so.
  fillVoices() {
    const abena = this.abenaVoices[this.language.id];
    const kind = this.gender;
    let options, help = "";
    if (abena) {
      const mine = abena.filter((v) => v.gender === kind);
      const list = mine.length ? mine : abena;
      if (!mine.length) help = `No ${kind} voice for ${this.language.name}. Showing all voices.`;
      options = list.map((v) => new Option(v.note ? `${v.name} (${v.note})` : v.name, v.name));
    } else if (this.serverVoices.length) {
      const mine = this.serverVoices.filter((name) => genderOf(name) === kind);
      options = (mine.length ? mine : this.serverVoices).map((name) => new Option(name, name));
      if (!mine.length) help = "These voices do not say if they are a woman or a man, so all are shown.";
    } else if (this.language.id === "auto") {
      options = [new Option(`Automatic ${kind}`, kind)];
      help = "The voice follows the language the reply is in.";
    } else {
      [options, help] = this.browserOptions(kind);
    }
    this.els.voice.replaceChildren(...options);
    const wanted = recall(this.voiceKey);
    if (options.some((option) => option.value === wanted)) this.els.voice.value = wanted;
    this.els.voice.disabled = options.length < 2;
    if (this.els.help) this.els.help.textContent = help;
  }

  // The browser's voices of this gender for this language. If none can be told apart by
  // name, list them all. Returns [options, help line].
  browserOptions(kind) {
    const voices = this.matchingBrowserVoices();
    const mine = voices.filter((voice) => genderOf(voice.name) === kind);
    if (mine.length) return [mine.map((v) => new Option(v.name, v.name)), ""];
    const label = (v) => new Option(`${v.name} (${v.lang})`, v.name);
    if (!voices.length) return [[new Option("Browser default", "")], "This browser has no voices to choose from."];
    const help = voices.some((v) => genderOf(v.name)) ? `No ${kind} voice found in this browser. Showing all voices.`
      : "This browser does not say which voices are a woman or a man, so all are shown.";
    return [[new Option("Browser default", ""), ...voices.map(label)], help];
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

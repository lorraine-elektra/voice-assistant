// Speaks sentences one after another, in the order they were queued.
// A sentence is spoken with Abena audio from the backend when there is some,
// otherwise with the browser's own voice.
export const canSpeak = "speechSynthesis" in window;
const AUDIO_WAIT_MS = 8000; // how long to wait for a sentence's audio before giving up

export class Player {
  constructor({ onStart, onIdle }) {
    this.onStart = onStart; // a sentence has started to sound
    this.onIdle = onIdle;   // the queue is empty
    this.queue = [];
    this.speaking = false;
    this.generation = 0;    // goes up on stop(), so late callbacks are ignored
    this.audio = new Audio();
  }

  // audio: optional promise of { audio: base64, mime } (or null if the backend could not make it).
  // tag: handed back to onStart, so the page knows which sentence is sounding.
  enqueue(text, audio = null, tag = null) {
    this.queue.push({ text, audio, tag });
    if (!this.speaking) this.next();
  }

  // Barge in: silence right now and forget everything queued.
  stop() {
    this.generation++;
    this.queue = [];
    this.speaking = false;
    clearTimeout(this.watchdog);
    this.audio.pause();
    if (canSpeak) speechSynthesis.cancel();
  }

  async next() {
    const item = this.queue.shift();
    if (!item) {
      this.speaking = false;
      this.onIdle();
      return;
    }
    this.speaking = true;
    const generation = this.generation;
    let finished = false;
    const finish = () => {
      if (finished || generation !== this.generation) return;
      finished = true;
      clearTimeout(this.watchdog);
      this.next();
    };
    const started = () => generation === this.generation && this.onStart(item.tag);

    const timeout = new Promise((resolve) => setTimeout(resolve, AUDIO_WAIT_MS, null));
    const clip = item.audio && (await Promise.race([item.audio, timeout]));
    if (generation !== this.generation) return; // stopped while waiting for the audio
    const useBrowser = () => generation === this.generation && this.speakWithBrowser(item.text, started, finish);
    if (clip) this.playAudio(clip, started, useBrowser, finish);
    else useBrowser();
  }

  playAudio(clip, started, fallback, finish) {
    this.audio.src = `data:${clip.mime};base64,${clip.audio}`;
    this.audio.onplaying = started;
    this.audio.onended = finish;
    this.audio.onerror = fallback;
    this.audio.play().catch(fallback);
  }

  speakWithBrowser(text, started, finish) {
    if (!canSpeak) {
      started();
      this.watchdog = setTimeout(finish, 300);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    if (this.lang) utterance.lang = this.lang;     // both set by the page from the pickers
    if (this.voice) utterance.voice = this.voice;
    let begun = false;
    utterance.onstart = () => { begun = true; started(); };
    utterance.onend = finish;
    // A language the browser has no voice for fails silently. Say it again with the browser's
    // default voice (it reads with the wrong accent, but the user hears the answer).
    utterance.onerror = (event) => {
      const cancelled = event.error === "canceled" || event.error === "interrupted";
      if (!begun && !cancelled && (this.lang || this.voice) && !retry) return this.speakWithBrowser(text, started, finish, true);
      finish();
    };
    // Some browsers never fire "end". Move on after a generous wait.
    clearTimeout(this.watchdog);
    this.watchdog = setTimeout(finish, 6000 + text.length * 90);
    if (retry) { utterance.lang = ""; utterance.voice = null; }
    speechSynthesis.speak(utterance);
  }
}

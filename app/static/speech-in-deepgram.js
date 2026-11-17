// Speech to text through the backend, which passes the audio on to Deepgram.
// Same shape as BrowserListener, so app.js can use either one.
export class DeepgramListener {
  // sendJson / sendBytes write to the WebSocket. Handlers are as in BrowserListener.
  constructor({ mic, sendJson, sendBytes, onInterim, onFinal }) {
    this.mic = mic;
    this.sendJson = sendJson;
    this.sendBytes = sendBytes;
    this.handlers = { onInterim, onFinal };
    this.active = false;   // true while audio should flow to the backend
    this.started = false;  // true once the backend has been told to open Deepgram
    mic.onChunk = (chunk) => this.active && this.started && this.sendBytes(chunk);
  }

  // While the assistant speaks this is switched off, so its own voice is never
  // transcribed. The backend keeps the Deepgram connection alive meanwhile.
  setActive(active) {
    this.active = active;
    if (active && !this.started && this.mic.sampleRate) {
      this.sendJson({ type: "audio_start", sample_rate: this.mic.sampleRate });
      this.started = true;
    }
  }

  // The backend already knows the new language (the page sends `settings` first).
  // Closing the connection makes the next setActive open a fresh one in that language.
  setLanguage(tag) {
    if (tag === this.lang) return;
    this.lang = tag;
    this.reset(true);
  }

  // After a barge in: send the moment of audio from just before it was detected,
  // so the first word the user said is not lost.
  sendPreroll() {
    if (this.started) this.mic.preroll.forEach((chunk) => this.sendBytes(chunk));
  }

  onTranscript(message) {
    if (!this.active) return;
    if (message.final) this.handlers.onFinal(message.text.trim());
    else this.handlers.onInterim(message.text);
  }

  // The connection was replaced or the mic was switched off.
  reset(tellBackend) {
    if (tellBackend && this.started) this.sendJson({ type: "audio_stop" });
    this.started = false;
    this.active = false;
  }
}

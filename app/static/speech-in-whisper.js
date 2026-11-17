// Speech to text through the backend, which sends each phrase to Whisper (Groq).
// The page listens for the user to start and stop talking, keeps that phrase as a
// WAV recording and sends it. Same shape as BrowserListener, so app.js can use either.
//
// The audio comes from the same 16 kHz stream the Mic already makes, so the moment
// just before the user started talking is kept and the first word is not clipped.
const START_LEVEL = 0.02;      // quieter than this is never speech
const START_TIMES_NOISE = 3;   // speech must be this much louder than the room
const END_TIMES_NOISE = 1.8;
const START_CHUNKS = 2;        // loud for this many chunks (0.1 s each) before we call it speech
const END_SILENCE_CHUNKS = 8;  // 0.8 s of quiet ends the phrase
const MIN_SPEECH_CHUNKS = 4;   // shorter than 0.4 s is a click or cough, not a phrase
const MAX_CHUNKS = 300;        // never record more than 30 s in one phrase
const PREROLL_CHUNKS = 3;

export function level(chunk) {
  const samples = new Int16Array(chunk);
  let sum = 0;
  for (const sample of samples) sum += (sample / 32768) ** 2;
  return Math.sqrt(sum / (samples.length || 1));
}

// 16 bit mono WAV, which every speech service understands.
export function toWav(chunks, sampleRate) {
  const bytes = chunks.reduce((total, chunk) => total + chunk.byteLength, 0);
  const wav = new DataView(new ArrayBuffer(44 + bytes));
  const text = (at, value) => [...value].forEach((char, i) => wav.setUint8(at + i, char.charCodeAt(0)));
  text(0, "RIFF");
  wav.setUint32(4, 36 + bytes, true);
  text(8, "WAVEfmt ");
  wav.setUint32(16, 16, true);
  wav.setUint16(20, 1, true);   // plain PCM
  wav.setUint16(22, 1, true);   // one channel
  wav.setUint32(24, sampleRate, true);
  wav.setUint32(28, sampleRate * 2, true);
  wav.setUint16(32, 2, true);
  wav.setUint16(34, 16, true);
  text(36, "data");
  wav.setUint32(40, bytes, true);
  let at = 44;
  for (const chunk of chunks) {
    new Uint8Array(wav.buffer, at, chunk.byteLength).set(new Uint8Array(chunk));
    at += chunk.byteLength;
  }
  return wav.buffer;
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export class WhisperListener {
  // sendJson writes to the WebSocket. Handlers are as in BrowserListener.
  constructor({ mic, sendJson, onInterim, onFinal }) {
    this.mic = mic;
    this.sendJson = sendJson;
    this.handlers = { onInterim, onFinal };
    this.active = false;
    this.clear();
    this.noise = 0.005;  // how loud the room is when nobody talks
    mic.onChunk = (chunk) => this.active && this.hear(chunk);
  }

  // While the assistant speaks this is off, so its own voice is never transcribed.
  setActive(active) {
    if (!active) this.clear();
    this.active = active;
  }

  // Whisper works out the language by itself, so there is nothing to do.
  setLanguage() {}

  // After a barge in: start the phrase with the audio from just before it was detected.
  sendPreroll() {
    if (!this.active || this.recording) return;
    this.recording = true;
    this.chunks = [...this.mic.preroll];
    this.handlers.onInterim("…");
  }

  hear(chunk) {
    const loudness = level(chunk);
    if (!this.recording) {
      this.preroll.push(chunk);
      if (this.preroll.length > PREROLL_CHUNKS) this.preroll.shift();
      const loud = loudness > Math.max(START_LEVEL, this.noise * START_TIMES_NOISE);
      if (!loud) this.noise = this.noise * 0.95 + loudness * 0.05;  // learn the room
      this.loudRun = loud ? this.loudRun + 1 : 0;
      if (this.loudRun >= START_CHUNKS) {
        this.recording = true;
        this.chunks = [...this.preroll];
        this.handlers.onInterim("…");
      }
      return;
    }
    this.chunks.push(chunk);
    const quiet = loudness < Math.max(START_LEVEL / 2, this.noise * END_TIMES_NOISE);
    this.quietRun = quiet ? this.quietRun + 1 : 0;
    if (!quiet) this.voiced++;
    if (this.quietRun >= END_SILENCE_CHUNKS || this.chunks.length >= MAX_CHUNKS) this.finish();
  }

  finish() {
    const enough = this.voiced >= MIN_SPEECH_CHUNKS;
    const chunks = this.chunks;
    this.clear();
    if (!enough) return this.handlers.onInterim("");
    this.handlers.onInterim("Transcribing…");
    const audio = toBase64(toWav(chunks, this.mic.sampleRate));
    this.sendJson({ type: "phrase", mime: "audio/wav", audio });
  }

  // The backend sends the words back as a final transcript.
  onTranscript(message) {
    if (message.final) this.handlers.onFinal(message.text.trim());
  }

  clear() {
    this.recording = false;
    this.chunks = [];
    this.preroll = [];
    this.loudRun = 0;
    this.quietRun = 0;
    this.voiced = 0;
  }

  reset() {
    this.clear();
    this.active = false;
  }
}

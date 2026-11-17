// The microphone. Two jobs:
//   1. Watch the sound level while the assistant speaks, to detect barge in.
//   2. In Deepgram mode, hand out raw audio chunks to send to the backend.
//
// The hard part of barge in is not reacting to the assistant's own voice coming out
// of the speakers. Three things guard against that:
//   1. The browser's echo cancellation is switched on for this microphone.
//   2. We keep a running average of the level while the assistant talks (its echo)
//      and only react to sound clearly louder than that average.
//   3. The sound has to stay loud for a moment, so a click or a cough is ignored.
const TICK_MS = 50;
const MIN_LEVEL = 0.05;      // never react to anything quieter than this
const TIMES_LOUDER = 3;      // how much louder than the echo the user must be
const HOLD_MS = 200;         // how long it must stay loud
const SETTLE_MS = 300;       // ignore the first moment while the average settles
const PREROLL_CHUNKS = 6;    // about 0.6 s of audio kept from just before a barge in

export const isPhone = /Android|iPhone|iPad/i.test(navigator.userAgent);

export function rms(samples) {
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.sqrt(sum / samples.length);
}

// Pure decision logic, kept apart from the audio plumbing so it is easy to follow.
export class VoiceDetector {
  reset() {
    this.echo = 0;
    this.loudMs = 0;
    this.elapsed = 0;
  }

  // Feed one level reading. Returns true when the user is clearly talking.
  hear(level) {
    this.elapsed += TICK_MS;
    const loud = level > Math.max(MIN_LEVEL, this.echo * TIMES_LOUDER);
    this.echo = this.echo * 0.95 + level * 0.05;
    if (this.elapsed < SETTLE_MS) return false;
    this.loudMs = loud ? this.loudMs + TICK_MS : Math.max(0, this.loudMs - TICK_MS);
    return this.loudMs >= HOLD_MS;
  }
}

export class Mic {
  constructor(onVoice) {
    this.onVoice = onVoice;   // the user started talking over the assistant
    this.onChunk = null;      // set by the Deepgram listener to receive raw audio
    this.preroll = [];        // the most recent chunks
    this.detector = new VoiceDetector();
  }

  get sampleRate() {
    return this.context?.sampleRate;
  }

  // Asks for the microphone. Throws if permission is denied.
  // rawAudio: also produce chunks of raw audio (needed for Deepgram only).
  async open({ rawAudio }) {
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.context = new AudioContext(rawAudio ? { sampleRate: 16000 } : {});
    const source = this.context.createMediaStreamSource(this.stream);
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 1024;
    source.connect(this.analyser);
    this.samples = new Float32Array(this.analyser.fftSize);
    if (rawAudio) {
      await this.context.audioWorklet.addModule("/static/pcm-worklet.js");
      const worklet = new AudioWorkletNode(this.context, "pcm-sender");
      worklet.port.onmessage = (event) => {
        this.preroll.push(event.data);
        if (this.preroll.length > PREROLL_CHUNKS) this.preroll.shift();
        this.onChunk?.(event.data);
      };
      source.connect(worklet);
    }
  }

  close() {
    this.unwatch();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.context?.close();
    this.stream = this.context = null;
    this.preroll = [];
  }

  // Call when the assistant starts speaking.
  watch() {
    if (!this.stream || this.timer) return;
    this.detector.reset();
    this.timer = setInterval(() => {
      this.analyser.getFloatTimeDomainData(this.samples);
      if (this.detector.hear(rms(this.samples))) {
        this.unwatch();
        this.onVoice();
      }
    }, TICK_MS);
  }

  unwatch() {
    clearInterval(this.timer);
    this.timer = null;
  }
}

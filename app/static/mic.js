// Watches the microphone level while the assistant speaks, to detect barge in.
//
// The hard part is not reacting to the assistant's own voice coming out of the
// speakers. Three things guard against that:
//   1. The browser's echo cancellation is switched on for this microphone.
//   2. We keep a running average of the level while the assistant talks (its echo)
//      and only react to sound clearly louder than that average.
//   3. The sound has to stay loud for a moment, so a click or a cough is ignored.
const TICK_MS = 50;
const MIN_LEVEL = 0.05;      // never react to anything quieter than this
const TIMES_LOUDER = 3;      // how much louder than the echo the user must be
const HOLD_MS = 200;         // how long it must stay loud
const SETTLE_MS = 300;       // ignore the first moment while the average settles

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

export class BargeInMonitor {
  constructor(onVoice) {
    this.onVoice = onVoice;
    this.detector = new VoiceDetector();
  }

  // Asks for the microphone. Throws if permission is denied.
  async open() {
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.context = new AudioContext();
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 1024;
    this.context.createMediaStreamSource(this.stream).connect(this.analyser);
    this.samples = new Float32Array(this.analyser.fftSize);
  }

  close() {
    this.unwatch();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.context?.close();
    this.stream = this.context = null;
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

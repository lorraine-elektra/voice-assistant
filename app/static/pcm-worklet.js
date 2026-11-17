// Runs on the audio thread. Collects microphone samples into small chunks of raw
// 16 bit audio (the format Deepgram is told to expect) and posts them to the page.
const CHUNK = 1600; // samples per chunk: a tenth of a second at 16 kHz

class PcmSender extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Int16Array(CHUNK);
    this.filled = 0;
  }

  process(inputs) {
    const samples = inputs[0][0];
    if (!samples) return true;
    for (const sample of samples) {
      this.chunk[this.filled++] = Math.max(-1, Math.min(1, sample)) * 32767;
      if (this.filled === CHUNK) {
        this.port.postMessage(this.chunk.slice().buffer);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-sender", PcmSender);

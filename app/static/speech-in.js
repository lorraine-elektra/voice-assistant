// Speech to text using the browser's own recogniser.
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
export const recognitionSupported = Boolean(Recognition);

const ERRORS = {
  "not-allowed": "Microphone permission was denied. Allow the microphone for this page in your browser settings, or type instead.",
  "service-not-allowed": "This browser blocked speech recognition. You can type instead.",
  "audio-capture": "No microphone was found. Plug one in, or type instead.",
  "network": "The browser's speech service could not be reached. You can type instead.",
};

export class BrowserListener {
  // onInterim(text): words so far. onFinal(text): a finished phrase.
  // onProblem(message, fatal): fatal means listening cannot continue.
  constructor({ onInterim, onFinal, onProblem }) {
    this.handlers = { onInterim, onFinal, onProblem };
    this.wanted = false;
    this.running = false;
  }

  setActive(active) {
    this.wanted = active;
    if (active && !this.running) this.begin();
    if (!active && this.running) this.recognition.abort();
  }

  begin() {
    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    recognition.onresult = (event) => this.onResult(event);
    recognition.onerror = (event) => this.onError(event.error);
    recognition.onend = () => {
      this.running = false;
      // The browser stops by itself after a pause. Start again if still wanted.
      if (this.wanted) setTimeout(() => this.wanted && !this.running && this.begin(), 250);
    };
    this.recognition = recognition;
    this.running = true;
    try {
      recognition.start();
    } catch {
      this.running = false;
    }
  }

  onResult(event) {
    if (!this.wanted) return;
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) this.handlers.onFinal(text.trim());
      else interim += text;
    }
    if (interim.trim()) this.handlers.onInterim(interim.trim());
  }

  onError(code) {
    if (code === "aborted") return;
    if (code === "no-speech") {
      this.handlers.onProblem("I did not hear anything. I am still listening.", false);
      return;
    }
    this.wanted = false;
    this.handlers.onProblem(ERRORS[code] || `Speech recognition stopped (${code}). You can type instead.`, true);
  }
}

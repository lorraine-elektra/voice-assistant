// Speaks sentences one after another, in the order they were queued.
export const canSpeak = "speechSynthesis" in window;

export class Player {
  constructor({ onStart, onIdle }) {
    this.onStart = onStart; // a sentence has started to sound
    this.onIdle = onIdle;   // the queue is empty
    this.queue = [];
    this.speaking = false;
    this.generation = 0;    // goes up on stop(), so late callbacks are ignored
  }

  enqueue(text) {
    this.queue.push(text);
    if (!this.speaking) this.next();
  }

  // Barge in: silence right now and forget everything queued.
  stop() {
    this.generation++;
    this.queue = [];
    this.speaking = false;
    clearTimeout(this.watchdog);
    if (canSpeak) speechSynthesis.cancel();
  }

  next() {
    const text = this.queue.shift();
    if (text === undefined) {
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
    this.play(text, generation, finish);
  }

  play(text, generation, finish) {
    if (!canSpeak) {
      this.onStart();
      this.watchdog = setTimeout(finish, 300);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onstart = () => generation === this.generation && this.onStart();
    utterance.onend = finish;
    utterance.onerror = finish;
    // Some browsers never fire "end". Move on after a generous wait.
    this.watchdog = setTimeout(finish, 6000 + text.length * 90);
    speechSynthesis.speak(utterance);
  }
}

// The page: connection, state, transcript. Message format is in docs/protocol.md.
import { Player, canSpeak } from "./speech-out.js";
import { BrowserListener, recognitionSupported } from "./speech-in.js";
import { DeepgramListener } from "./speech-in-deepgram.js";
import { Mic, isPhone } from "./mic.js";

const $ = (id) => document.getElementById(id);
const els = {
  transcript: $("transcript"), hint: $("hint"), banner: $("banner"), mic: $("mic"),
  micLabel: $("mic-label"), status: $("status"), stop: $("stop"), form: $("typed"),
  text: $("text"), modes: $("modes"), latency: $("latency"),
};
const LABELS = {
  connecting: "Connecting", offline: "Connection lost. Reconnecting", idle: "Idle",
  listening: "Listening", thinking: "Thinking", searching: "Searching the web", speaking: "Speaking",
};
const GOAL_MS = 1500;
const MIC_DENIED = "Microphone permission was denied. Allow the microphone for this page in your browser settings, or type instead.";

const state = {
  connected: false,
  everConnected: false,
  micOn: false,
  backend: null,     // "thinking" or "searching" while the backend works on a reply
  turn: 0,           // counts user messages, exactly like the backend does
  activeTurn: null,  // the turn whose reply we accept. Anything else is stale.
  brain: "?",
  stt: "browser",    // who turns speech into text: "browser" or "deepgram"
  tts: "browser",    // who speaks: "browser" or "elevenlabs"
};
let socket;
let retries = 0;
let pendingBubble = null;       // live words while the user is still talking
const replyBubbles = new Map(); // turn -> the assistant's bubble
const audioWaiters = new Map(); // sentence index -> function that delivers its audio
let timing = null;              // measures end of speech to first spoken word
let listener = null;            // BrowserListener or DeepgramListener, see chooseListener

const player = new Player({ onStart: () => { reportLatency(); sync(); }, onIdle: () => sync() });
const mic = new Mic(() => {
  interrupt(true);
  listener?.sendPreroll?.();
});
const listenerHandlers = {
  onInterim: (text) => { hideBanner(); showPending(text); },
  onFinal: (text) => {
    clearPending();
    if (text) sendUserText(text);
    else showBanner("I did not catch that. Please say it again.");
  },
  onProblem: (message, fatal) => {
    showBanner(message);
    if (fatal) setMic(false);
  },
};

function chooseListener() {
  listener?.setActive(false);
  if (state.stt === "deepgram") {
    const sendBytes = (chunk) => socket.readyState === WebSocket.OPEN && socket.send(chunk);
    listener = new DeepgramListener({ mic, sendJson: send, sendBytes, ...listenerHandlers });
  } else {
    mic.onChunk = null;
    listener = recognitionSupported ? new BrowserListener(listenerHandlers) : null;
  }
  els.mic.disabled = !listener;
  if (!listener) {
    els.micLabel.textContent = "Voice input is not supported in this browser";
    if (els.hint.isConnected) {
      els.hint.textContent = "Voice input is not supported in this browser. Type your message below instead.";
    }
    if (state.micOn) setMic(false);
  }
}

// ---------- state on screen ----------

function currentState() {
  if (!state.connected) return state.everConnected ? "offline" : "connecting";
  if (state.backend === "searching") return "searching";
  if (player.speaking) return "speaking";
  if (state.backend) return "thinking";
  return state.micOn ? "listening" : "idle";
}

function sync() {
  const now = currentState();
  els.status.textContent = LABELS[now];
  els.mic.dataset.state = now;
  els.mic.setAttribute("aria-pressed", String(state.micOn));
  if (listener) els.micLabel.textContent = state.micOn ? "Stop listening" : "Start listening";
  els.stop.hidden = !["thinking", "searching", "speaking"].includes(now);
  // Do not transcribe the assistant's own voice: stop listening while it speaks
  // and let the level monitor watch for the user instead.
  if (listener) listener.setActive(state.micOn && state.connected && !player.speaking);
  if (state.micOn && player.speaking) mic.watch();
  else mic.unwatch();
}

// Shows which service does each job right now.
function showModes() {
  const modes = [
    ["Brain", state.brain],
    ["Listening", listener ? state.stt : "typing only"],
    ["Voice", state.tts === "elevenlabs" || canSpeak ? state.tts : "text only"],
  ];
  els.modes.replaceChildren(...modes.map(([name, value]) => {
    const item = document.createElement("li");
    item.append(`${name}: `, Object.assign(document.createElement("b"), { textContent: value }));
    return item;
  }));
}

function showBanner(message) {
  els.banner.textContent = message;
  els.banner.hidden = false;
}

function hideBanner() {
  els.banner.hidden = true;
}

// ---------- transcript ----------

function addBubble(role, text) {
  els.hint.remove();
  const bubble = document.createElement("p");
  bubble.className = `bubble ${role}`;
  const who = Object.assign(document.createElement("span"), {
    className: "who", textContent: role === "user" ? "You" : "Assistant",
  });
  const words = Object.assign(document.createElement("span"), { className: "words", textContent: text });
  bubble.append(who, words);
  els.transcript.append(bubble);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  return bubble;
}

function replyBubble(turn) {
  if (!replyBubbles.has(turn)) replyBubbles.set(turn, addBubble("assistant", ""));
  return replyBubbles.get(turn);
}

function showPending(text) {
  if (!pendingBubble) {
    pendingBubble = addBubble("user", "");
    pendingBubble.classList.add("pending");
  }
  pendingBubble.querySelector(".words").textContent = text;
}

function clearPending() {
  pendingBubble?.remove();
  pendingBubble = null;
}

function addSources(turn, sources) {
  const list = Object.assign(document.createElement("ul"), { className: "sources" });
  for (const source of sources) {
    if (!/^https?:\/\//.test(source.url)) continue;
    const link = Object.assign(document.createElement("a"), {
      href: source.url, textContent: source.title || source.url, target: "_blank", rel: "noopener noreferrer",
    });
    const item = document.createElement("li");
    item.append("Source: ", link);
    list.append(item);
  }
  replyBubble(turn).append(list);
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function addNote(turn, text) {
  replyBubble(turn).append(Object.assign(document.createElement("span"), { className: "note", textContent: text }));
}

// ---------- talking to the backend ----------

function send(message) {
  if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function sendUserText(raw) {
  const text = raw.trim();
  if (!text) return showBanner("I did not catch that. Please try again.");
  if (!state.connected) return showBanner("Not connected yet. Your message was not sent.");
  hideBanner();
  interrupt(false); // the backend cancels the old reply itself when a new message arrives
  state.turn++;
  state.activeTurn = state.turn;
  state.backend = "thinking";
  timing = { turn: state.turn, from: performance.now(), searched: false };
  addBubble("user", text);
  send({ type: "user_text", text });
  sync();
}

// Barge in or Stop: go quiet at once and ignore the rest of the current reply.
function interrupt(tellBackend) {
  const busy = Boolean(state.backend) || player.speaking;
  player.stop();
  audioWaiters.forEach((deliver) => deliver(null));
  audioWaiters.clear();
  timing = null;
  if (busy) replyBubbles.get(state.activeTurn)?.classList.add("cut");
  if (busy && tellBackend) send({ type: "stop" });
  state.activeTurn = null;
  state.backend = null;
  sync();
}

// Time from the end of the user's speech to the first spoken word of the reply.
function reportLatency() {
  if (!timing || timing.turn !== state.activeTurn) return;
  const ms = Math.round(performance.now() - timing.from);
  const { turn, searched } = timing;
  timing = null;
  const verdict = searched ? "included a web search" : ms <= GOAL_MS ? "within the 1.5 s goal" : "over the 1.5 s goal";
  els.latency.textContent = `First spoken word after ${(ms / 1000).toFixed(2)} s (${verdict})`;
  els.latency.hidden = false;
  send({ type: "latency", turn, ms, searched });
}

function onReady(message) {
  Object.assign(state, { brain: message.brain, stt: message.stt, tts: message.tts });
  chooseListener();
  showModes();
  sync();
}

function onSttFailed(message) {
  showBanner(message.message);
  state.stt = "browser"; // fall back to the browser's own speech recognition
  chooseListener();
  showModes();
  sync();
}

function onMessage(message) {
  if (message.type === "ready") return onReady(message);
  if (message.type === "stt_failed") return onSttFailed(message);
  if (message.type === "transcript") return listener?.onTranscript?.(message);
  if (message.type === "error" && message.turn === undefined) return showBanner(message.message);
  if (message.turn !== state.activeTurn) return; // from a reply we already cancelled
  const turn = message.turn;
  if (message.type === "status") {
    state.backend = message.state;
    if (message.state === "searching" && timing) timing.searched = true;
  }
  if (message.type === "sentence") {
    const words = replyBubble(turn).querySelector(".words");
    words.textContent = `${words.textContent} ${message.text}`.trim();
    els.transcript.scrollTop = els.transcript.scrollHeight;
    // With ElevenLabs the audio for this sentence follows in its own message.
    const audio = state.tts === "elevenlabs"
      ? new Promise((deliver) => audioWaiters.set(message.index, deliver))
      : null;
    player.enqueue(message.text, audio);
  }
  if (message.type === "audio") audioWaiters.get(message.index)?.(message.audio);
  if (message.type === "sources") addSources(turn, message.sources);
  if (message.type === "search_failed") addNote(turn, "The web search did not work, so this answer is from memory.");
  if (message.type === "done") state.backend = null;
  if (message.type === "error") {
    state.backend = null;
    showBanner(message.message);
  }
  sync();
}

function connect() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${location.host}/ws`);
  socket.binaryType = "arraybuffer";
  socket.onopen = () => {
    state.connected = state.everConnected = true;
    state.turn = 0; // a new connection is a new conversation on the backend
    retries = 0;
    sync();
  };
  socket.onmessage = (event) => onMessage(JSON.parse(event.data));
  socket.onclose = () => {
    state.connected = false;
    listener?.reset?.(false);
    interrupt(false);
    setTimeout(connect, Math.min(10000, 1000 * 2 ** retries++));
  };
}

// ---------- controls ----------

async function setMic(on) {
  state.micOn = on;
  if (!on) {
    listener?.reset?.(true);
    mic.close();
    clearPending();
    return sync();
  }
  hideBanner();
  interrupt(true); // pressing the mic while it talks also counts as barge in
  const deepgram = state.stt === "deepgram";
  // With browser recognition, phones cannot share the mic with the level monitor.
  if (isPhone && !deepgram) return;
  try {
    await mic.open({ rawAudio: deepgram });
    sync();
  } catch {
    // Browser recognition reports a denied permission by itself. Deepgram cannot.
    if (deepgram) {
      showBanner(MIC_DENIED);
      setMic(false);
    }
  }
}

els.mic.addEventListener("click", () => setMic(!state.micOn));
els.stop.addEventListener("click", () => interrupt(true));
document.addEventListener("keydown", (event) => event.key === "Escape" && interrupt(true));
els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendUserText(els.text.value);
  els.text.value = "";
});

chooseListener();
showModes();
sync();
connect();

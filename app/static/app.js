// The page: connection, state, transcript. Message format is in docs/protocol.md.
import { Player, canSpeak } from "./speech-out.js";
import { BrowserListener, recognitionSupported } from "./speech-in.js";
import { BargeInMonitor, isPhone } from "./mic.js";

const $ = (id) => document.getElementById(id);
const els = {
  transcript: $("transcript"), hint: $("hint"), banner: $("banner"), mic: $("mic"),
  micLabel: $("mic-label"), status: $("status"), stop: $("stop"), form: $("typed"),
  text: $("text"), modes: $("modes"),
};
const LABELS = {
  connecting: "Connecting", offline: "Connection lost. Reconnecting", idle: "Idle",
  listening: "Listening", thinking: "Thinking", searching: "Searching the web", speaking: "Speaking",
};

const state = {
  connected: false,
  everConnected: false,
  micOn: false,
  backend: null,     // "thinking" or "searching" while the backend works on a reply
  turn: 0,           // counts user messages, exactly like the backend does
  activeTurn: null,  // the turn whose reply we accept. Anything else is stale.
  brain: "?",
};
let socket;
let retries = 0;
let pendingBubble = null;     // live words while the user is still talking
const replyBubbles = new Map(); // turn -> the assistant's bubble

const player = new Player({ onStart: () => sync(), onIdle: () => sync() });
const monitor = new BargeInMonitor(() => interrupt(true));
const listener = recognitionSupported && new BrowserListener({
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
});

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
  els.micLabel.textContent = state.micOn ? "Stop listening" : "Start listening";
  els.stop.hidden = !["thinking", "searching", "speaking"].includes(now);
  // Do not transcribe the assistant's own voice: pause recognition while it speaks
  // and let the level monitor watch for the user instead.
  if (listener) listener.setActive(state.micOn && state.connected && !player.speaking);
  if (state.micOn && player.speaking) monitor.watch();
  else monitor.unwatch();
}

function showModes() {
  const modes = [
    ["Brain", state.brain],
    ["Listening", recognitionSupported ? "browser" : "typing only"],
    ["Voice", canSpeak ? "browser" : "text only"],
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
  els.hint?.remove();
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
  socket.send(JSON.stringify(message));
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
  addBubble("user", text);
  send({ type: "user_text", text });
  sync();
}

// Barge in or Stop: go quiet at once and ignore the rest of the current reply.
function interrupt(tellBackend) {
  const busy = Boolean(state.backend) || player.speaking;
  player.stop();
  if (busy) replyBubbles.get(state.activeTurn)?.classList.add("cut");
  if (busy && tellBackend && state.connected) send({ type: "stop" });
  state.activeTurn = null;
  state.backend = null;
  sync();
}

function onMessage(message) {
  if (message.type === "ready") {
    state.brain = message.brain;
    return showModes();
  }
  if (message.type === "error" && message.turn === undefined) return showBanner(message.message);
  if (message.turn !== state.activeTurn) return; // from a reply we already cancelled
  const turn = message.turn;
  if (message.type === "status") state.backend = message.state;
  if (message.type === "sentence") {
    const words = replyBubble(turn).querySelector(".words");
    words.textContent = `${words.textContent} ${message.text}`.trim();
    els.transcript.scrollTop = els.transcript.scrollHeight;
    player.enqueue(message.text);
  }
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
  socket.onopen = () => {
    state.connected = state.everConnected = true;
    state.turn = 0; // a new connection is a new conversation on the backend
    retries = 0;
    sync();
  };
  socket.onmessage = (event) => onMessage(JSON.parse(event.data));
  socket.onclose = () => {
    state.connected = false;
    interrupt(false);
    setTimeout(connect, Math.min(10000, 1000 * 2 ** retries++));
  };
}

// ---------- controls ----------

async function setMic(on) {
  state.micOn = on;
  if (!on) {
    monitor.close();
    clearPending();
    return sync();
  }
  hideBanner();
  interrupt(true); // pressing the mic while it talks also counts as barge in
  if (isPhone) return; // phones cannot share the mic with speech recognition
  try {
    await monitor.open();
    sync();
  } catch {
    // No level monitor. Recognition reports a denied permission by itself.
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

if (!recognitionSupported) {
  els.mic.disabled = true;
  els.micLabel.textContent = "Voice input is not supported in this browser";
  els.hint.textContent = "Voice input is not supported in this browser. Type your message below instead.";
}
showModes();
sync();
connect();

// The page: connection, state, transcript. Message format is in docs/protocol.md.
import { Player, canSpeak } from "./speech-out.js";
import { Choices } from "./choices.js";
import { BrowserListener, recognitionSupported } from "./speech-in.js";
import { PhraseListener } from "./speech-in-phrase.js";
import { Mic, isPhone } from "./mic.js";
import { robot, restyle } from "./robot.js";

const $ = (id) => document.getElementById(id);
const els = {
  setup: $("setup"), setupForm: $("setup-form"), chat: $("chat"), openSetup: $("open-setup"),
  start: $("start"), name: $("name"), previewName: $("preview-name"), stage: $("stage"), botName: $("bot-name"),
  transcript: $("transcript"), hint: $("hint"), banner: $("banner"), mic: $("mic"),
  micLabel: $("mic-label"), status: $("status"), stop: $("stop"), form: $("typed"),
  text: $("text"), modes: $("modes"), latency: $("latency"), latencyText: $("latency-text"),
  latencyBar: $("latency-bar"), wave: $("wave"),
};
const LABELS = {
  connecting: "Connecting", offline: "Connection lost. Reconnecting", idle: "Idle",
  listening: "Listening", thinking: "Thinking", searching: "Searching the web", speaking: "Speaking",
  preparing: "Preparing the voice",
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
  tts: "browser",    // who speaks Twi and Pidgin: "browser" or "abena"
  abena: false,      // Abena is on: it speaks, and listens for, Twi and Pidgin
};
let socket;
let retries = 0;
let pendingBubble = null;       // live words while the user is still talking
const replyBubbles = new Map(); // turn -> the assistant's bubble
const audioWaiters = new Map(); // sentence index -> function that delivers its audio
let timing = null;              // measures end of speech to first spoken word
let listener = null;            // BrowserListener or PhraseListener, see chooseListener

const player = new Player({
  onStart: (sentence) => { markLive(sentence); reportLatency(); sync(); },
  onIdle: () => { markLive(null); sync(); },
  onWait: () => sync(),
});
const choices = new Choices({
  languageEl: $("language"), voiceEl: $("voice"), helpEl: $("voice-help"),
  genderEls: document.querySelectorAll('input[name="gender"]'), onChange: applyChoices,
});

// ---------- setup: name, voice type, language, voice ----------

const assistantName = () => els.name.value.trim() || "Assistant";
const robots = {
  preview: robot("assistant", choices.gender),
  you: robot("you", "woman"),
  bot: robot("assistant", choices.gender),
};
$("preview-robot").append(robots.preview);
$("you-robot").append(robots.you);
$("bot-robot").append(robots.bot);

// Everything that shows the assistant's name or look follows the setup form.
function showAssistant() {
  const name = els.name.value.trim();
  els.previewName.textContent = name || "Your assistant";
  els.botName.textContent = assistantName();
  for (const el of [robots.preview, robots.bot]) if (el.dataset.gender !== choices.gender) restyle(el, choices.gender);
}

function showSetup(open) {
  els.setup.hidden = !open;
  els.chat.hidden = open;
  els.openSetup.hidden = open;
  if (open) {
    els.start.textContent = setupDone ? "Save changes" : "Start talking";
    els.name.focus();
  } else {
    els.text.focus();
  }
}

let setupDone = false; // nothing is stored, so every refresh starts at the setup screen
els.name.addEventListener("input", showAssistant);
els.openSetup.addEventListener("click", () => showSetup(true));
els.setupForm.addEventListener("submit", (event) => {
  event.preventDefault();
  setupDone = true;
  showAssistant();
  applyChoices();
  showSetup(false);
});
const mic = new Mic(() => {
  interrupt(true);
  listener?.sendPreroll?.();
});
const listenerHandlers = {
  onInterim: (text) => { hideBanner(); if (text) showPending(text); else clearPending(); },
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

// Who listens for the current language: the backend (Abena, for Twi and Pidgin) or the
// browser's own recognition (everything else, including automatic).
const LOCAL = ["tw", "pcm-GH", "pcm-NG"];
const backendListens = () => state.abena && LOCAL.includes(choices.language.id);
let listenerKind = null;

function chooseListener() {
  listener?.setActive(false);
  listenerKind = backendListens() ? "backend" : "browser";
  if (listenerKind === "backend") {
    listener = new PhraseListener({ mic, sendJson: send, ...listenerHandlers });
  } else {
    mic.onChunk = null;
    listener = recognitionSupported ? new BrowserListener(listenerHandlers) : null;
  }
  listener?.setLanguage(choices.tag);
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
  if (player.waiting) return "preparing"; // the sentence is on screen, its Abena audio is not here yet
  if (player.speaking) return "speaking";
  if (state.backend) return "thinking";
  return state.micOn ? "listening" : "idle";
}

function sync() {
  const now = currentState();
  const look = now === "preparing" ? "thinking" : now; // preparing looks like thinking
  els.status.textContent = LABELS[now];
  els.mic.dataset.state = look;
  els.stage.dataset.state = look; // the robots move with this
  els.mic.setAttribute("aria-pressed", String(state.micOn));
  if (listener) els.micLabel.textContent = state.micOn ? "Stop listening" : "Start listening";
  els.stop.hidden = !["thinking", "searching", "preparing", "speaking"].includes(now);
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
    ["Listening", listener ? (listenerKind === "browser" ? "browser" : "abena") : "typing only"],
    ["Voice", state.tts === "abena" ? "browser + abena" : canSpeak ? "browser" : "text only"],
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

// One turn: a small robot and a speech bubble. You sit on the left, the assistant on the right.
function addBubble(role, text) {
  els.hint.remove();
  const bubble = document.createElement("div");
  bubble.className = `turn ${role}`;
  const mine = role === "user";
  const who = Object.assign(document.createElement("span"), {
    className: "who", textContent: mine ? "You" : assistantName(),
  });
  const words = Object.assign(document.createElement("span"), { className: "words", textContent: text });
  const content = Object.assign(document.createElement("div"), { className: "content" });
  content.append(who, words);
  bubble.append(robot(mine ? "you" : "assistant", mine ? "woman" : choices.gender), content);
  els.transcript.append(bubble);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  return bubble;
}

// The sentence being spoken right now gets an underline.
function markLive(sentence) {
  els.transcript.querySelectorAll(".s.live").forEach((span) => span.classList.remove("live"));
  sentence?.classList.add("live");
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
  replyBubble(turn).querySelector(".content").append(list);
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function addNote(turn, text) {
  replyBubble(turn).querySelector(".content").append(Object.assign(document.createElement("span"), { className: "note", textContent: text }));
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
  markLive(null);
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
  els.latencyText.textContent = `First word after ${(ms / 1000).toFixed(2)} s, ${verdict}`;
  els.latencyBar.style.width = `${Math.min(100, (ms / GOAL_MS) * 100)}%`;
  els.latencyBar.classList.toggle("over", ms > GOAL_MS);
  els.latency.hidden = false;
  send({ type: "latency", turn, ms, searched });
}

// The language or voice picker changed: tell the browser voice, the backend and the listener.
// The backend must hear it first, so it speaks the next reply with the right voice.
function applyChoices() {
  player.lang = choices.tag;
  player.voice = choices.browserVoice;
  send({ ...choices.message, name: els.name.value.trim() });
  showAssistant();
  // A language can need a different listener (Twi needs Abena, English can use the browser).
  if (listener && listenerKind !== (backendListens() ? "backend" : "browser")) {
    const wasOn = state.micOn;
    if (wasOn) setMic(false);
    chooseListener();
    showModes();
    if (wasOn) setMic(true);
  }
  listener?.setLanguage(choices.tag);
  sync();
}

function onReady(message) {
  Object.assign(state, { brain: message.brain, tts: message.tts, abena: Boolean(message.abena) });
  choices.setOptions(message);
  chooseListener();
  applyChoices();
  showModes();
  sync();
}

function onMessage(message) {
  if (message.type === "ready") return onReady(message);
  if (message.type === "transcript") return listener?.onTranscript?.(message);
  if (message.type === "error" && message.turn === undefined) return showBanner(message.message);
  if (message.turn !== state.activeTurn) return; // from a reply we already cancelled
  const turn = message.turn;
  if (message.type === "status") {
    state.backend = message.state;
    if (message.state === "searching" && timing) timing.searched = true;
  }
  if (message.type === "language") {
    // Gemini says which language the reply is in. In automatic mode the browser voice follows it.
    const spoken = choices.voiceFor(message.language);
    if (spoken) Object.assign(player, { lang: spoken.tag, voice: spoken.voice });
  }
  if (message.type === "sentence") {
    const words = replyBubble(turn).querySelector(".words");
    const sentence = Object.assign(document.createElement("span"), { className: "s", textContent: message.text });
    if (words.childNodes.length) words.append(" ");
    words.append(sentence);
    els.transcript.scrollTop = els.transcript.scrollHeight;
    // When the backend makes audio for this sentence, it follows in its own message.
    const audio = message.audio_expected
      ? new Promise((deliver) => audioWaiters.set(message.index, deliver))
      : null;
    player.enqueue(message.text, audio, sentence);
  }
  if (message.type === "audio") audioWaiters.get(message.index)?.(message.audio && { audio: message.audio, mime: message.mime || "audio/wav" });
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
  const rawAudio = backendListens(); // then we need raw audio to record phrases
  // With browser recognition, phones cannot share the mic with the level monitor.
  if (isPhone && !rawAudio) return;
  try {
    await mic.open({ rawAudio });
    sync();
  } catch {
    // Browser recognition reports a denied permission by itself. Our own recorder cannot.
    if (rawAudio) {
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

// ---------- the strip: one line that shows who has the floor ----------

const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const cssColor = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
let smoothLevel = 0;

function drawWave(now) {
  const canvas = els.wave;
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const mode = currentState();
  const t = reducedMotion.matches ? 0 : now / 1000;
  smoothLevel += ((mode === "listening" ? mic.level() : 0) - smoothLevel) * 0.25;
  let color = cssColor("--rule"), amp = 0.02, speed = 0, dash = [];
  if (mode === "listening") { color = cssColor("--cobalt"); amp = 0.06 + smoothLevel * 0.9; speed = 6; }
  if (mode === "speaking") { color = cssColor("--green"); amp = 0.35; speed = 3; }
  if (mode === "thinking" || mode === "preparing") color = cssColor("--muted");
  if (mode === "searching") { color = cssColor("--muted"); dash = [2, 8]; }
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  ctx.setLineDash(dash);
  ctx.beginPath();
  for (let x = 0; x <= width; x += 3) {
    const edge = Math.sin((x / width) * Math.PI);  // calm at both ends
    const wobble = Math.sin(x / 14 + t * speed) * Math.sin(x / 41 - t * speed * 0.6);
    const y = height / 2 + wobble * amp * (height / 2) * edge;
    x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
  if (!reducedMotion.matches) requestAnimationFrame(drawWave);
}
const redraw = () => requestAnimationFrame(drawWave);
reducedMotion.addEventListener("change", redraw);
window.addEventListener("resize", () => reducedMotion.matches && redraw());
new MutationObserver(() => reducedMotion.matches && redraw()).observe(els.status, { childList: true });
redraw();

chooseListener();
showModes();
showAssistant();
sync();
showSetup(true);
connect();

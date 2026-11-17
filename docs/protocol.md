# WebSocket message format

The browser and the backend talk over one WebSocket at `/ws`. Every text message is a
JSON object with a `type` field. This file is the agreement between frontend and backend.

A **turn** is one user message and the reply to it. The backend numbers turns 1, 2, 3
and stamps every reply message with its turn, so the browser can ignore anything stale.

## Browser to backend

| type | fields | meaning |
| --- | --- | --- |
| `user_text` | `text` | What the user said or typed, at most 2000 characters. Starts a new turn. If a reply is still in progress it is cancelled first (barge in). |
| `stop` | | Cancel the reply in progress. |
| `settings` | `language`, `voice`, `name` | The language, voice and assistant name picked on the page. `name` is optional, at most 30 characters, and goes into the prompt so the assistant answers to it. `language` is an `id` from `ready`. `voice` is a name from `ready` (an Abena voice), `woman` or `man` (with the automatic language), or empty. Applies from the next reply. An unknown language gets an `error` and changes nothing. An unknown voice means the default voice. |
| `phrase` | `audio`, `mime` | Twi and Pidgin only, when `abena` is true. One finished phrase the user spoke, as base64 WAV (16 kHz, mono, 16 bit). The page finds the start and end of the phrase itself. The backend sends it to Abena for the language in `settings` and answers with a final `transcript`, or an `error` without a `turn` if it could not hear it. At most 2,000,000 base64 characters. |
| `latency` | `turn`, `ms`, `searched` | Measured time from end of speech to first spoken word. The backend logs it. |

**Binary messages** are not used. The backend ignores them.

The backend only accepts the socket from its own page: a browser `Origin` header that does
not match the `Host` is closed with code 1008.

## Backend to browser

| type | fields | meaning |
| --- | --- | --- |
| `ready` | `brain`, `tts`, `abena`, `languages`, `abena_voices` | Sent once after connecting. Says which mode is active: `brain` is `mock` or `gemini`, `tts` is `browser` or `abena`. `abena` is true when Abena speaks, and listens for, Twi and Pidgin. The browser listens for everything else. `languages` is the list to pick from, each `{"id", "name", "browser"}` where `browser` is the tag for the browser's own speech recognition and voices. `abena_voices` maps a language id (`tw`, `pcm-GH`, `pcm-NG`) to its Abena voices, each `{"name", "gender", "note"}`, empty in mock mode. Never contains a key or a voice id. |
| `status` | `turn`, `state` | What the backend is doing. `state` is `thinking` or `searching` (a web search is running). |
| `language` | `turn`, `language` | Gemini mode only. The language the reply is written in, an `id` from `ready`. Sent before the first `sentence` of the turn. |
| `sentence` | `turn`, `index`, `text`, `audio_expected` | One finished sentence of the reply. `index` counts from 0 inside the turn. Speak them in order. `audio_expected` is true when an `audio` message for this sentence follows, so the browser waits for it. |
| `audio` | `turn`, `index`, `audio`, `mime` | Abena only. The sound of the sentence with the same `index`, as base64. `mime` is `audio/wav`. `audio` is `null` if it could not be made, and then the browser speaks that sentence itself. May arrive out of order. Play by `index`. |
| `search_failed` | `turn` | The web search did not work. The reply carries on from what the assistant already knows. |
| `sources` | `turn`, `sources` | Web pages the answer used, as a list of `{"title", "url"}`. Show them as links. Never speak them. |
| `done` | `turn` | The reply is complete. All its audio has been sent. |
| `cancelled` | `turn` | The reply was cancelled. Nothing more arrives for this turn. |
| `transcript` | `text`, `final` | The answer to a `phrase`, and only final ones. The words heard in a phrase. When `final` is true the phrase is finished and the browser sends it back as `user_text`. |
| `error` | `message`, maybe `turn` | Something went wrong. `message` is safe to show to the user. Gemini's free limit and a timeout have their own wording. |

## Barge in rule

When `user_text` or `stop` arrives, the backend stops the reply in progress before it
does anything else, including a web search or audio that is still being prepared.
After `cancelled`, no `sentence` or `audio` for that turn is ever sent.

## Example

```
browser  {"type": "user_text", "text": "Hello there"}
backend  {"type": "status", "turn": 1, "state": "thinking"}
backend  {"type": "sentence", "turn": 1, "index": 0, "text": "Hi!"}
backend  {"type": "sentence", "turn": 1, "index": 1, "text": "How can I help?"}
backend  {"type": "done", "turn": 1}
```

## Example with a web search

When a search starts the backend sends the `searching` status and then a short filler
sentence ("Let me look that up.") to speak, so there is no long silence.

```
browser  {"type": "user_text", "text": "What is the weather in Paris today?"}
backend  {"type": "status", "turn": 2, "state": "thinking"}
backend  {"type": "status", "turn": 2, "state": "searching"}
backend  {"type": "sentence", "turn": 2, "index": 0, "text": "Let me look that up."}
backend  {"type": "status", "turn": 2, "state": "thinking"}
backend  {"type": "sentence", "turn": 2, "index": 1, "text": "According to ..."}
backend  {"type": "sources", "turn": 2, "sources": [{"title": "...", "url": "https://..."}]}
backend  {"type": "done", "turn": 2}
```

## Example with real voice (Gemini and Abena, Twi picked)

```
browser  {"type": "settings", "language": "tw", "voice": "Abena"}
browser  {"type": "phrase", "mime": "audio/wav", "audio": "<base64 wav>"}
backend  {"type": "transcript", "text": "Ɛte sɛn?", "final": true}
browser  {"type": "user_text", "text": "Ɛte sɛn?"}
backend  {"type": "status", "turn": 1, "state": "thinking"}
backend  {"type": "language", "turn": 1, "language": "tw"}
backend  {"type": "sentence", "turn": 1, "index": 0, "text": "Me ho yɛ.", "audio_expected": true}
backend  {"type": "audio", "turn": 1, "index": 0, "audio": "<base64 wav>", "mime": "audio/wav"}
backend  {"type": "done", "turn": 1}
browser  {"type": "latency", "turn": 1, "ms": 1400, "searched": false}
```

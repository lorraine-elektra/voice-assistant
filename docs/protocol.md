# WebSocket message format

The browser and the backend talk over one WebSocket at `/ws`. Every text message is a
JSON object with a `type` field. This file is the agreement between frontend and backend.

A **turn** is one user message and the reply to it. The backend numbers turns 1, 2, 3
and stamps every reply message with its turn, so the browser can ignore anything stale.

## Browser to backend

| type | fields | meaning |
| --- | --- | --- |
| `user_text` | `text` | What the user said or typed. Starts a new turn. If a reply is still in progress it is cancelled first (barge in). |
| `stop` | | Cancel the reply in progress. |
| `settings` | `language`, `voice`, `name` | The language, voice and assistant name picked on the page. `name` is optional, at most 30 characters, and goes into the prompt so the assistant answers to it. `language` is an `id` from `ready`. `voice` is a name from `ready` (an Abena or ElevenLabs voice), `woman` or `man` (with the automatic language), or empty. Applies from the next reply. An unknown language gets an `error` and changes nothing. An unknown voice means the default voice. Send it before `audio_start`, so Deepgram listens in the right language. |
| `phrase` | `audio`, `mime` | Whisper mode only. One finished phrase the user spoke, as base64 WAV (16 kHz, mono, 16 bit). The page finds the start and end of the phrase itself. The backend answers with a final `transcript`, or an `error` without a `turn` if it could not hear it. |
| `audio_start` | `sample_rate` | Deepgram mode only. Open the speech to text connection. Audio follows as binary messages. |
| `audio_stop` | | Close the speech to text connection. |
| `latency` | `turn`, `ms`, `searched` | Measured time from end of speech to first spoken word. The backend logs it. |

**Binary messages** are microphone audio: raw 16 bit mono samples at the `sample_rate`
given in `audio_start`. They are ignored unless Deepgram is connected.

## Backend to browser

| type | fields | meaning |
| --- | --- | --- |
| `ready` | `brain`, `stt`, `tts`, `languages`, `voices` | Sent once after connecting. Says which mode is active: `brain` is `mock` or `gemini`, `stt` is `browser`, `deepgram` or `whisper`, `tts` is `browser` or `elevenlabs`. `abena` is true when Abena speaks Twi and Pidgin. `languages` is the list to pick from, each `{"id", "name", "browser"}` where `browser` is the tag for the browser's own speech recognition and voices. `abena_voices` maps a language id (`tw`, `pcm-GH`, `pcm-NG`) to its Abena voices, each `{"name", "gender", "note"}`, empty without an Abena key. `voices` is the list of ElevenLabs voice names, empty when the browser speaks. Never contains a key or a voice id. |
| `status` | `turn`, `state` | What the backend is doing. `state` is `thinking` or `searching` (a web search is running). |
| `language` | `turn`, `language` | Gemini mode only. The language the reply is written in, an `id` from `ready`. Sent before the first `sentence` of the turn. |
| `sentence` | `turn`, `index`, `text`, `audio_expected` | One finished sentence of the reply. `index` counts from 0 inside the turn. Speak them in order. `audio_expected` is true when an `audio` message for this sentence follows, so the browser waits for it. |
| `audio` | `turn`, `index`, `audio`, `mime` | ElevenLabs or Abena. The sound of the sentence with the same `index`, as base64. `mime` is `audio/mpeg` (ElevenLabs) or `audio/wav` (Abena, used for Twi and Pidgin). `audio` is `null` if it could not be made, and then the browser speaks that sentence itself. May arrive out of order. Play by `index`. |
| `search_failed` | `turn` | The web search did not work. The reply carries on from what the assistant already knows. |
| `sources` | `turn`, `sources` | Web pages the answer used, as a list of `{"title", "url"}`. Show them as links. Never speak them. |
| `done` | `turn` | The reply is complete. All its audio has been sent. |
| `cancelled` | `turn` | The reply was cancelled. Nothing more arrives for this turn. |
| `transcript` | `text`, `final` | Deepgram and Whisper modes. (Whisper sends only final ones.) Words heard so far. When `final` is true the phrase is finished and the browser sends it back as `user_text`. |
| `stt_failed` | `message` | Deepgram could not be used. The browser falls back to its own speech recognition. |
| `error` | `message`, maybe `turn` | Something went wrong. `message` is safe to show to the user. |

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

## Example with real voice (Deepgram and ElevenLabs)

```
browser  {"type": "audio_start", "sample_rate": 16000}
browser  <binary audio> <binary audio> ...
backend  {"type": "transcript", "text": "hello", "final": false}
backend  {"type": "transcript", "text": "Hello there.", "final": true}
browser  {"type": "user_text", "text": "Hello there."}
backend  {"type": "status", "turn": 1, "state": "thinking"}
backend  {"type": "sentence", "turn": 1, "index": 0, "text": "Hi!"}
backend  {"type": "audio", "turn": 1, "index": 0, "audio": "<base64 mp3>"}
backend  {"type": "done", "turn": 1}
browser  {"type": "latency", "turn": 1, "ms": 900, "searched": false}
```

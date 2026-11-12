# Voice Assistant spec (draft)

This is a draft. The owner reviews it and changes anything that is wrong before building starts.

## Goal
A voice assistant that feels fast and can be interrupted, deployed at a public URL, with a clear README and a short demo.

## Users and flow
1. The user opens the web page and presses the mic button.
2. The browser sends audio (or, in Phase 1, recognised text) to the backend over a WebSocket.
3. The backend sends the text to Claude and streams the reply back.
4. The reply is cut into sentences. Each finished sentence is spoken as soon as it is ready.
5. If the user starts talking while the assistant is speaking, the assistant stops and listens (barge in).

## Phases

### Phase 1: text brain, browser voice
* FastAPI app with a `/health` route and a WebSocket route
* Browser speech recognition for input and browser speech synthesis for output
* Claude streaming, with replies cut into sentences
* Barge in: a new message cancels the reply in progress
* Mock mode so everything runs without keys
* Tests for the sentence splitter, the mock reply and the WebSocket flow

### Phase 2: real voice
* Deepgram live speech to text
* ElevenLabs text to speech, one request per sentence
* Browser fallbacks if a key is missing
* Needs: `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`

### Phase 3: ship it
* Deploy on Railway with a public URL
* Measure time to first spoken word and write it in the README. Initial goal is under 1.5 seconds, to be confirmed by measuring
* Short demo clip and a README with a diagram
* A small set of test conversations used as a regression check

## Out of scope for now
* User accounts and login
* Saving conversation history
* Phone calls

## Inputs the owner provides
* `ANTHROPIC_API_KEY` (Phase 1 live testing)
* `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (Phase 2)
* Railway account (Phase 3)
* Her own signups and payments, handled by her

## Open questions
* Which Claude model for replies? Default in `.env.example` is a fast one, change if quality matters more than speed.
* Should the assistant have a persona or a fixed topic?

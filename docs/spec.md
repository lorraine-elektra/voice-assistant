# Voice Assistant spec

This describes what is built. If the code and this file disagree, tell the owner.

## Goal
A voice assistant that feels fast, can be interrupted, and understands and answers in
English, French, Spanish, Twi, Ghana Pidgin and Naija Pidgin, on free tiers.
It runs on the owner's machine. Deployment is a later step.

## Users and flow
1. The user opens the web page and presses the mic button, or types.
2. The page records each phrase (it finds the start and end itself) and sends it to the backend as WAV. Without a Groq key the browser's own speech recognition sends text instead.
3. Groq Whisper turns the phrase into text and detects the language. If Whisper was guessing, Abena's speech recognition gives a second opinion.
4. The backend sends the text to Gemini, which returns JSON: the language of the reply and the reply, streamed.
5. The reply is cut into sentences. Each finished sentence is spoken as soon as it is ready: by the browser for English, French and Spanish, by Abena voices for Twi and both Pidgins.
6. If the user starts talking, types or presses Stop while the assistant is answering, the assistant stops and listens (barge in).

The message format is in `docs/protocol.md`.

## What is built

### Text loop
* FastAPI app with `/health`, the page at `/`, and a WebSocket at `/ws`
* Gemini streaming with the model from `GEMINI_MODEL`, answering as JSON (`detected_language`, `reply_text`). The language comes first so the page knows which voice to use before the first word
* Conversation history kept in memory for the life of the connection only
* Replies cut into sentences (handles abbreviations, decimals, missing punctuation)
* Barge in: a new message or `stop` cancels the reply at once, and nothing from the old reply arrives afterwards
* Mock mode (the default) so everything runs with no keys
* System prompt: a general assistant that answers in one to three short spoken sentences, with no markdown, lists or emojis. The assistant can be given a name on the page

### Web lookup
* **Not available with real Gemini.** Gemini may not allow Google Search together with JSON output. This is unchecked
* Mock mode still fakes a search, and a failing search, with canned results, so the page flow (searching status, filler line, source links) stays tested

### Page
* One page, plain HTML and JavaScript
* Mic button, live transcript, and a status: idle, listening, thinking, searching, speaking
* Phrase recorder: 16 kHz WAV, 0.8 s of quiet ends a phrase, sounds shorter than 0.4 s are ignored, the moment before speech starts is kept
* Barge in by voice using a microphone level monitor that ignores the assistant's own voice
* Text box that always works, and is the fallback when speech recognition is not supported
* Friendly messages for mic permission denied, connection lost (with automatic reconnect), backend errors, and empty or unclear speech
* Works with the keyboard alone (Esc stops) and on a phone sized screen

### Services
* Groq Whisper (`whisper-large-v3`) for speech to text, with the language detected by Whisper. It reports how sure it was
* Abena speech to text as a second opinion, only when Whisper was unsure (its free quota is 10 to 20 transcriptions)
* Abena text to speech for Twi and both Pidgins, one request per sentence (500 characters at most), returned as WAV and played in order
* A missing key means that piece falls back to the browser. A failed sentence is spoken by the browser. The page shows the active modes
* Keys stay on the backend
* Time from end of speech to first spoken word is measured, shown in the page and logged. Goal: under 1.5 seconds
* Regression conversations in `tests/conversations.json`

### Languages and voices
* A language picker: Detect automatically (the default), English, Spanish, French, Naija Pidgin, Ghana Pidgin and Ghana Twi. The table is `app/languages.py`
* In automatic mode Gemini says which language it replied in and the page picks the voice for it. A chosen language is forced on Gemini
* A Woman or Man choice, then a voice. Twi: Abena, Ama, Yaa (women), Kofi (man). Ghana Pidgin: Kobby, Kwabena (men), Akua (woman). Naija Pidgin: James (man), Chioma (woman). The table is `app/abena_voices.py`
* Abena has one Twi man and no Pidgin woman. The Pidgin women and Kwabena are its English voices with a Ghanaian or Nigerian accent reading Pidgin text
* Other languages list the browser's voices of the picked kind. The kind is guessed from the voice's name, because browsers do not say. Spanish and French voices must be installed on the computer
* Voice ids never reach the browser. The choices are remembered in the browser

## Not built yet
* Web search with Gemini
* Deploy to a public URL (Railway)
* Short demo clip
* Measured speed with the real services (needs the owner's keys)

## Out of scope for now
* User accounts and login
* Saving conversation history
* Phone calls

## Inputs the owner provides
* `GEMINI_API_KEY` and `GEMINI_MODEL` for replies and language detection
* `GROQ_API_KEY` for speech to text
* `ABENA_API_KEY` is optional. The Abena playground API works without it (Twi and Pidgin voices, Twi second opinion)
* Her own signups and payments, handled by her

## Open questions
* Is the Abena Pidgin voice good enough, or should YarnGPT be added for Naija Pidgin?
* Should the assistant have a persona or a fixed topic? For now it is a general assistant.

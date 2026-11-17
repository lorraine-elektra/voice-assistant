# Voice Assistant spec

This describes what is built. If the code and this file disagree, tell the owner.

## Goal
A voice assistant that feels fast, can be interrupted, and understands and answers in
English, French, Spanish, Twi, Ghana Pidgin and Naija Pidgin, on free tiers.
It runs on the owner's machine. Deployment is a later step.

## Users and flow
1. The user opens the web page and presses the mic button, or types.
2. The browser's own speech recognition turns speech into text, in the language picked on the page (English when the picker is on automatic).
3. When Twi or a Pidgin is picked, the page records each phrase instead (it finds the start and end itself) and sends it to the backend as WAV, where Abena's speech recognition turns it into text.
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
* A question that was stopped or failed before any answer is forgotten, so the next reply does not answer it too
* Gemini's free limit (429) and a timeout each get their own message. A request that stalls before any text is tried once more
* Only the app's own page may open the WebSocket (Origin check). Messages are limited to 2000 characters, a phrase to about 30 seconds
* Mock mode (the default) so everything runs with no keys. Real Gemini needs `MOCK_MODE=false`, `GEMINI_API_KEY` and `GEMINI_MODEL`
* System prompt: a general assistant that answers in one to three short spoken sentences, with no markdown, lists or emojis. The assistant can be given a name on the page

### Web lookup
* **Not available with real Gemini.** Checked in November 2026: on the free tier the Google Search tool answers 429 (no quota), with or without JSON output. The assistant says it has no live internet access
* Mock mode still fakes a search, and a failing search, with canned results, so the page flow (searching status, filler line, source links) stays tested

### Page
* One page, plain HTML and JavaScript
* Mic button, live transcript, and a status: idle, listening, thinking, searching, speaking
* Phrase recorder (Twi and Pidgin only): 16 kHz WAV, 0.8 s of quiet ends a phrase, sounds shorter than 0.4 s are ignored, the moment before speech starts is kept
* Barge in by voice using a microphone level monitor that ignores the assistant's own voice
* Text box that always works, and is the fallback when speech recognition is not supported
* Friendly messages for mic permission denied, connection lost (with automatic reconnect), backend errors, and empty or unclear speech
* Works with the keyboard alone (Esc stops) and on a phone sized screen

### Services
* Browser speech recognition for English, Spanish, French and the automatic setting. It listens in one language at a time, so automatic detection works on the words, not on the sound: spoken Twi or Pidgin is only understood when that language is picked
* Abena speech to text for Twi and both Pidgins (its free quota is 10 to 20 transcriptions). When it refuses, the page asks the user to type
* Abena text to speech for Twi and both Pidgins, one request per sentence (500 characters at most), returned as WAV and played in order. The page waits up to 15 seconds for a sentence's audio and shows "Preparing the voice" meanwhile
* In mock mode Abena is off and the browser does all the listening and speaking. A failed sentence is spoken by the browser, with its default voice if it has none for the language. The page shows the active modes
* Keys stay on the backend
* Time from end of speech to first spoken word is measured, shown in the page and logged. Goal: under 1.5 seconds
* Regression conversations in `tests/conversations.json`

### Languages and voices
* A language picker: Detect automatically (the default), English, Spanish, French, Naija Pidgin, Ghana Pidgin and Ghana Twi. The table is `app/languages.py`
* In automatic mode Gemini says which language it replied in and the page picks the voice for it. A chosen language is forced on Gemini
* A Woman or Man choice, then a voice. Twi: Abena, Ama, Yaa (women), Kofi (man). Ghana Pidgin: Kobby, Kwabena (men), Akua (woman). Naija Pidgin: James (man), Chioma (woman). The table is `app/abena_voices.py`
* Abena has one Twi man and no Pidgin woman. The Pidgin women and Kwabena are its English voices with a Ghanaian or Nigerian accent reading Pidgin text
* Other languages list the browser's voices of the picked kind. The kind is guessed from the voice's name, because browsers do not say. Spanish and French voices must be installed on the computer
* Voice ids never reach the browser. Nothing is stored in the browser: a refresh starts again from the setup screen and the defaults

## Not built yet
* Web search with Gemini
* Deploy to a public URL (Railway)
* Short demo clip
* Measured speed when speaking into a real microphone (typed: 1.7 to 1.8 s with a browser voice, about 8 s with an Abena voice)
* Listening that detects the spoken language by itself (Groq Whisper did this and was removed)

## Out of scope for now
* User accounts and login
* Saving conversation history
* Phone calls

## Inputs the owner provides
* `GEMINI_API_KEY` and `GEMINI_MODEL` for replies and language detection
* `ABENA_API_KEY` is optional. The Abena playground API works without it (Twi and Pidgin voices and listening)
* Her own signups and payments, handled by her

## Open questions
* Is the Abena Pidgin voice good enough, or should YarnGPT be added for Naija Pidgin?
* Should the assistant have a persona or a fixed topic? For now it is a general assistant.

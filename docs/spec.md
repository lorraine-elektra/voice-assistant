# Voice Assistant spec

This describes what is built. If the code and this file disagree, tell the owner.

## Goal
A voice assistant that feels fast, can be interrupted, and can look things up on the web.
It runs on the owner's machine. Deployment is a later step.

## Users and flow
1. The user opens the web page and presses the mic button, or types.
2. The browser sends recognised text to the backend over a WebSocket. In Deepgram mode it sends audio and the backend returns the text.
3. The backend sends the text to Claude and streams the reply back.
4. The reply is cut into sentences. Each finished sentence is spoken as soon as it is ready.
5. If the question needs current information, Claude searches the web. The page shows a searching status and says a short filler line.
6. If the user starts talking, types or presses Stop while the assistant is answering, the assistant stops and listens (barge in).

The message format is in `docs/protocol.md`.

## What is built

### Text loop
* FastAPI app with `/health`, the page at `/`, and a WebSocket at `/ws`
* Claude streaming with the model from `ANTHROPIC_MODEL`
* Conversation history kept in memory for the life of the connection only
* Replies cut into sentences (handles abbreviations, decimals, missing punctuation)
* Barge in: a new message or `stop` cancels the reply at once, and nothing from the old reply arrives afterwards
* Mock mode (the default) so everything runs with no keys
* System prompt: a general assistant that answers in one to three short spoken sentences, with no markdown, lists or emojis

### Web lookup
* Uses Anthropic's built in web search tool (`web_search_20250305`), which runs on Anthropic's side
* Claude decides when to search. Small talk gets no search
* A spoken "Let me look that up" and a `searching` status cover the wait
* Spoken answers name the source in a few words. URLs are never spoken. Links are shown in the transcript
* `WEB_SEARCH_MAX_USES` limits searches per reply
* Barge in cancels a search in progress
* A failed search is said plainly and the answer comes from what Claude already knows
* Mock mode fakes a search, and a failing search, with canned results

### Page
* One page, plain HTML and JavaScript
* Mic button, live transcript, and a status: idle, listening, thinking, searching, speaking
* Browser speech recognition and browser speech synthesis by default
* Barge in by voice using a microphone level monitor that ignores the assistant's own voice
* Text box that always works, and is the fallback when speech recognition is not supported
* Friendly messages for mic permission denied, connection lost (with automatic reconnect), backend errors, and empty or unclear speech
* Works with the keyboard alone (Esc stops) and on a phone sized screen

### Real voice
* Deepgram live speech to text, audio streamed from the browser through the backend
* ElevenLabs text to speech, one request per sentence, played in order
* Barge in stops playback and drops audio still being prepared
* A missing key means that piece falls back to the browser. The page shows the active modes
* Keys stay on the backend
* Time from end of speech to first spoken word is measured, shown in the page and logged. Goal: under 1.5 seconds without a search
* Regression conversations in `tests/conversations.json`

### Languages and voices
* A language picker: English, Spanish, French, Naija Pidgin, Ghana Pidgin and Ghana Twi. The table is `app/languages.py`
* The choice tells Claude which language to reply in, tells Deepgram or the browser which language to listen for, and translates the search filler line
* A voice picker. With browser speech it lists the browser's voices for that language. With ElevenLabs it lists the names from `ELEVENLABS_VOICE_ID` and `ELEVENLABS_VOICES`. Voice ids never reach the browser
* Both choices are remembered in the browser and apply from the next reply
* Known limits (checked against the docs, November 2026): neither Deepgram nor ElevenLabs supports Pidgin, so Pidgin is heard with the English recogniser and spoken by whichever voice is picked. Deepgram Nova-3 hears Twi (as Akan, `ak`), but no ElevenLabs or common browser voice speaks it, so spoken Twi sounds rough and the transcript is the reliable part. Browser recognition of Twi depends on the browser, and the page says so if it cannot

## Migration to a free tier cascade (in progress, approved)
Replacing Claude, Deepgram and ElevenLabs with Groq Whisper (speech to text), Gemini
(`gemini-2.5-flash`, reply and language detection in one JSON call), Abena AI (Twi and both Pidgin voices, Twi speech fallback). Abena has one Twi man (Kofi) and no Pidgin woman, so the Pidgin women are its English voices with a Ghanaian or Nigerian accent. YarnGPT is skipped unless the Abena Naija Pidgin voice sounds wrong. English, French and Spanish
are spoken by the browser voice.
* Done: Abena text to speech and routing (Twi, Ghana Pidgin and Naija Pidgin use Abena voices when `ABENA_API_KEY` is set), Abena speech to text module, Gemini brain (`app/gemini.py`), Groq module (`app/whisper.py`), `auto` language, `language` message, config
* Done too: the page records each phrase (it detects start and end itself, sends 16 kHz WAV) and Groq Whisper transcribes it. Low confidence phrases get Abena as a second opinion. Voice pickers: Abena voices by name for Twi and Pidgin, a woman and a man from the browser's voices for other languages, woman or man when the language is automatic
* Not done: removing Deepgram and ElevenLabs
* Web search is dropped for now. Gemini may not allow Google Search together with JSON output, to be checked
* Blocked on the owner: keys, and the Abena and YarnGPT API docs

## Not built yet
* Deploy to a public URL (Railway)
* Short demo clip
* Measured speed with the real services (needs the owner's keys)

## Out of scope for now
* User accounts and login
* Saving conversation history
* Phone calls

## Inputs the owner provides
* `ANTHROPIC_API_KEY` for real replies and web search
* `DEEPGRAM_API_KEY` for Deepgram
* `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` for ElevenLabs
* Optional `ELEVENLABS_VOICES` (`Name:id` pairs) for more voices in the picker, for example Nigerian and Ghanaian accented ones
* Her own signups and payments, handled by her

## Open questions
* Which Claude model for replies? The default in `.env.example` is a fast one. Change it if quality matters more than speed.
* Should the assistant have a persona or a fixed topic? For now it is a general assistant.

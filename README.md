# Voice Assistant

A real time voice assistant that runs in the browser. You talk, Gemini answers, and the
answer is spoken back sentence by sentence. It works out which language you spoke
(English, French, Spanish, Twi, Ghana Pidgin or Naija Pidgin) and answers in it. You can
interrupt it mid sentence (barge in).

It runs with **no API keys at all** in mock mode, and switches each piece to the real
service as soon as its key is in `.env`. The free tiers of Groq, Google AI Studio and
Abena are enough to try it.

## How it flows

```mermaid
flowchart LR
    subgraph Browser
        Mic[Microphone] --> Rec[Phrase recorder: WAV]
        Mic -. no Groq key .-> STTb[Browser speech recognition]
        Rec --> WS((WebSocket))
        STTb --> WS
        WS --> Player[Sentence player]
        Player --> Speaker[Speaker]
        Mic --> Level[Level monitor] -- barge in --> Player
    end
    subgraph Backend [FastAPI backend]
        WS <--> Session[Session: history, turns, barge in]
        Session --> Brain{Mock or Gemini}
        Brain --> Split[Sentence splitter] --> Session
        Session -. phrase .-> Whisper[Groq Whisper]
        Session -. low confidence .-> AbenaASR[Abena speech to text]
        Session -. Twi and Pidgin sentence .-> AbenaTTS[Abena voices]
    end
    Brain <--> Gemini[(Gemini API)]
    Whisper <--> Groq[(Groq)]
    AbenaASR <--> Abena[(Abena AI)]
    AbenaTTS <--> Abena
```

Solid lines are always used. Dotted lines are only used when that service's key is set.

1. The page listens for you to start and stop talking and sends each phrase to the backend as a WAV recording. Without a Groq key the browser's own speech recognition is used instead.
2. Groq Whisper turns the phrase into text and detects the language by itself. If Whisper was guessing (which often happens with Twi), Abena's speech recognition gives a second opinion.
3. The text goes to Gemini, which answers as JSON: the language it replies in, and the reply. The reply is streamed.
4. The reply is cut into sentences. Each finished sentence is sent at once. English, French and Spanish are spoken by the browser's voices. Twi and both Pidgins are spoken by Abena voices.
5. If you talk, type or press Stop while it is answering, the reply is cancelled on both sides.

The exact messages are written down in [docs/protocol.md](docs/protocol.md).

## Setup

Needs Python 3.11 or newer.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

On macOS or Linux the second command is `source .venv/bin/activate`.

## Run

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000 in Chrome or Edge. Press the microphone and talk, or type.
The badges in the top right show which mode each piece is in.

### Using real services

Copy `.env.example` to `.env`, set `MOCK_MODE=false`, and fill in the keys you have.
Each piece falls back by itself if its key is missing:

| Piece | With its key | Without |
| --- | --- | --- |
| Replies and language detection | Gemini (`GEMINI_API_KEY`, model in `GEMINI_MODEL`) | Canned mock replies |
| Listening | Groq Whisper (`GROQ_API_KEY`) | Browser speech recognition |
| Voice for Twi and Pidgin | Abena (no key needed, `ABENA_API_KEY` optional) | Browser speech synthesis |

English, French and Spanish are always spoken by the browser, so they use no credits.
Keys stay on the backend. The browser is only told the mode names and the voice names.

### Language and voice

The language picker defaults to "Detect automatically". Pick a language to force it.
Choose Woman or Man, then a voice. Twi and Pidgin offer Abena's voices by name. Abena has
only one Twi man (Kofi) and no Pidgin woman, so the Pidgin women (Akua, Chioma) are its
English voices with a Ghanaian or Nigerian accent reading the Pidgin text. Other languages
list the browser's voices, so Spanish and French need those voices installed on your
computer.

### Limits of the free tiers

* **Abena** allows 20 requests a minute and 100 an hour without a key, and the text to
  speech trial is small. Speech recognition from Abena is only asked when Whisper was
  unsure, to save its 10 to 20 free transcriptions.
* **Gemini and Groq** have their own free quotas. If one runs out, the page shows a short
  error message and you can type instead.
* Web search is not available with Gemini yet. Mock mode still fakes one for the page.

### Trying the mock

In mock mode, a message with a word like *weather*, *news*, *price* or *search* gets a
fake web search. Add the word *unreachable* to see a search that fails.

## Test

```bash
pytest
```

All tests run with no keys and no network. Gemini, Groq and Abena are faked.
`tests/conversations.json` holds whole conversations that are replayed in mock mode as a
regression check. Add one whenever you fix a bug.

## Speed

The page measures the time from the end of your speech to the first spoken word, shows
it under the status, and the backend logs it. The goal is under 1.5 seconds for answers
in a browser voice.

| Setup | Measured | Notes |
| --- | --- | --- |
| Mock replies, browser voice | 0.9 to 1.3 s | Measured in an embedded Chromium while building. Almost all of it is the browser voice starting up. |
| Real Groq, Gemini and Abena | not measured yet | Needs real keys. Run it, read the number under the status, and write it here. It includes the 0.8 s the recorder waits to be sure you finished. |

## Known limits

* **Barge in by voice depends on your speakers.** The page ignores the assistant's own
  voice using echo cancellation plus a loudness check, but loud speakers close to the
  microphone can still trigger it or mask you. Headphones are the reliable setup. The
  Stop button, the Esc key and typing always work.
* The recorder decides a phrase is over after 0.8 s of quiet. Pauses longer than that
  split a sentence in two.
* Whisper can invent words from background noise. Very short sounds are ignored.
* Whisper does not officially support Twi, and Abena's second opinion has a small free
  quota. Typing always works.
* With browser speech recognition (no Groq key), the first word or two of a barge in can
  be lost, and on phones barge in by voice is off. Use Stop. With Groq it works on phones.
* Browser speech recognition needs Chrome, Edge or Safari. Firefox gets the text box.
* Sentences that end in an abbreviation such as "etc." are joined with the next one.
* Conversation history lives in memory for the life of the connection. A reconnect
  starts a new conversation.
* Not deployed anywhere. It runs on your own machine.

## Project layout

```
app/main.py          routes: the page, /health, /ws
app/session.py       one connection: history, turns, barge in, phrases, audio
app/brain.py         picks mock or Gemini
app/gemini.py        Gemini streaming, reads the JSON reply as it arrives
app/whisper.py       Groq Whisper request and its confidence check
app/abena.py         Abena speech to text and text to speech
app/abena_voices.py  the Abena voices offered per language
app/languages.py     the languages and their prompts
app/mock.py          canned replies and fake search
app/sentences.py     cuts a text stream into sentences
app/static/          the page (plain HTML, CSS and JavaScript)
docs/                spec and message format
tests/               pytest tests and regression conversations
```

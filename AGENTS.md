# Voice Assistant: instructions for AI coding agents

Read this file at the start of every session. It is the memory of the project.

## What this project is
A real time voice assistant. The user speaks into the browser, the backend turns speech into text, Claude replies in a streamed answer, and the reply is spoken back sentence by sentence. The user can interrupt it mid sentence (barge in).

Full requirements live in `docs/spec.md`. If the code and the spec disagree, tell the owner and fix the code unless told otherwise.

## Stack
* Python 3.11 or newer, FastAPI, WebSockets
* Anthropic API for the replies (streaming)
* Deepgram for live speech to text (Phase 2)
* ElevenLabs for text to speech (Phase 2)
* Plain HTML and JavaScript frontend, no framework
* pytest for tests

## Commands
* Install: `pip install -r requirements.txt`
* Run: `uvicorn app.main:app --reload`
* Test: `pytest`

## Rules
* Mock mode is the default (`MOCK_MODE=true`). The app and all tests must work with no API keys at all.
* Never commit secrets. Keys live in `.env`, which is git ignored. Update `.env.example` whenever a new variable is added.
* Never invent API keys, voice ids or model names. If an input is missing, stop and ask the owner for it.
* Every change that adds behaviour needs a test. Run `pytest` before saying a task is done.
* Plan before coding. For anything bigger than a small fix, write the plan first and wait for approval.
* Small commits with clear messages, one idea per commit.
* Keep files short and readable. Prefer simple code over clever code.

## How to work with the owner
* The owner is a CS student building this for her AI engineering portfolio. Claude writes the code, the owner supplies inputs (API keys, choices, testing on her machine).
* Explain decisions in plain English, briefly. No long lectures.
* When the owner asks to understand a concept, give a plain English description first, then stepped clues, instead of dumping a full solution.
* At the end of a task, list what was done, what is left, and any inputs needed from the owner.

## Current phase
Phase 1. See `docs/spec.md` for the phase list.

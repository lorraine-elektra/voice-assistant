# Voice Assistant

A real time voice assistant you can interrupt. Speak, get a streamed spoken answer, and cut in whenever you want.

Status: Phase 1 in progress. See `docs/spec.md` for the plan.

## Run it locally
1. Create a virtual environment and install the requirements:
   `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`. Leave `MOCK_MODE=true` to run without any API keys.
3. Start the server:
   `uvicorn app.main:app --reload`
4. Check it works by opening `http://localhost:8000/health`.

## Run the tests
`pytest`

## Project layout
* `app/` the FastAPI backend
* `tests/` automated tests
* `docs/spec.md` requirements and phases
* `AGENTS.md` instructions for AI coding agents working on this repo

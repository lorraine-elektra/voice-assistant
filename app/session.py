"""One Session per WebSocket connection: history, the reply in progress, and barge in."""
import asyncio
import base64
import json
import logging
import time

import httpx
from fastapi import WebSocket

from app import abena, abena_voices
from app.brain import reply_events
from app.config import settings
from app.languages import DEFAULT, LANGUAGES, for_browser
from app.sentences import SentenceSplitter

log = logging.getLogger("voice")
ERROR_TEXT = "Sorry, something went wrong on my side. Please try again."
BUSY_TEXT = "The assistant has reached its free usage limit for now. Please wait a minute and try again."
SLOW_TEXT = "The assistant took too long to answer. Please try again."
ABENA_LIMIT_TEXT = "Abena could not hear that. Its free speech limit may be used up, so please type your message instead."
PHRASE_FAILED_TEXT = "I could not hear that. Please try again."
TOO_LONG_TEXT = "That message is too long. Please make it shorter."
MAX_TEXT = 2000             # characters in one typed or spoken message
MAX_AUDIO_CHARS = 2_000_000  # base64 of one phrase: 30 s of 16 kHz WAV is about 1.3 million


def error_text(error: Exception) -> str:
    """What to tell the user when a reply fails. Never includes details or keys."""
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
        return BUSY_TEXT
    if isinstance(error, httpx.TimeoutException):
        return SLOW_TEXT
    return ERROR_TEXT


class Session:
    def __init__(self, websocket: WebSocket) -> None:
        self.ws = websocket
        self.history: list[dict] = []  # lives only as long as the connection
        self.turn = 0
        self.language = DEFAULT  # all three set by the `settings` message
        self.voice = ""
        self.name = ""  # what the user calls the assistant
        self.reply_task: asyncio.Task | None = None
        self.phrase_tasks: set[asyncio.Task] = set()  # phrases being transcribed
        self.http: httpx.AsyncClient | None = None  # reused for every Abena request
        self._send_lock = asyncio.Lock()

    async def send(self, **message) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        await self.send(
            type="ready", brain=settings.brain_mode, tts=settings.tts_mode,
            languages=for_browser(), abena=settings.abena_mode,
            abena_voices=abena_voices.for_browser() if settings.abena_mode else {},
        )
        try:
            while True:
                frame = await self.ws.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                if frame.get("text") is not None:  # binary frames are not used, ignore them
                    await self.on_text_frame(frame["text"])
        finally:
            await self.cancel_reply(notify=False)
            for task in self.phrase_tasks:
                task.cancel()
            if self.http:
                await self.http.aclose()

    async def on_text_frame(self, raw: str) -> None:
        try:
            message = json.loads(raw)
            kind = message["type"]
        except (ValueError, KeyError, TypeError):
            await self.send(type="error", message="I could not read that message.")
            return
        if kind == "user_text":
            text = str(message.get("text", "")).strip()
            if not text:
                await self.send(type="error", message="I did not catch that. Please try again.")
                return
            if len(text) > MAX_TEXT:
                await self.send(type="error", message=TOO_LONG_TEXT)
                return
            await self.cancel_reply()
            self.turn += 1
            self.reply_task = asyncio.create_task(self.reply(self.turn, text))
        elif kind == "stop":
            await self.cancel_reply()
        elif kind == "settings":
            wanted = message.get("language")
            language = LANGUAGES.get(wanted) if isinstance(wanted, str) else None
            if language is None:
                await self.send(type="error", message="That language is not available.")
                return
            self.language = language
            self.voice = str(message.get("voice") or "")
            self.name = " ".join(str(message.get("name") or "").split())[:30]
        elif kind == "phrase":
            task = asyncio.create_task(self.hear_phrase(message))
            self.phrase_tasks.add(task)
            task.add_done_callback(self.phrase_tasks.discard)
        elif kind == "latency":
            log.info(
                "Turn %s: %s ms from end of speech to first spoken word (web search: %s)",
                message.get("turn"), message.get("ms"), bool(message.get("searched")),
            )
        else:
            await self.send(type="error", message=f"Unknown message type: {kind}")

    # ---------- speech to text: Abena hears Twi and Pidgin, the browser hears the rest ----------

    async def hear_phrase(self, message: dict) -> None:
        """One recorded phrase from the browser. The words go back as a final transcript."""
        try:
            if not isinstance(message["audio"], str) or len(message["audio"]) > MAX_AUDIO_CHARS:
                raise ValueError("The phrase is not text, or is too large")
            audio = base64.b64decode(message["audio"])
            mime = str(message.get("mime") or "audio/wav")
            if self.http is None:
                self.http = httpx.AsyncClient()
            if not (settings.abena_mode and self.language.id in abena.LISTENS_FOR):
                raise RuntimeError("No speech to text service for this language")
            try:  # Abena's free use is limited, so a refusal gets its own message
                text = await abena.transcribe(self.http, audio, mime, self.language.id)
            except httpx.HTTPStatusError as error:
                log.warning("Abena could not transcribe: %s", error)
                await self.send(type="error", message=ABENA_LIMIT_TEXT)
                return
            await self.send(type="transcript", text=text, final=True)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.warning("Could not transcribe a phrase: %s", error)
            await self.send(type="error", message=PHRASE_FAILED_TEXT)

    # ---------- the reply ----------

    async def cancel_reply(self, notify: bool = True) -> None:
        """Barge in. Once this returns, the old reply can send nothing more."""
        task = self.reply_task
        self.reply_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if notify:
            await self.send(type="cancelled", turn=self.turn)

    async def send_audio(self, turn: int, index: int, text: str, language_id: str) -> None:
        """Turn one sentence into audio. On failure send null so the browser speaks it."""
        audio = mime = None
        try:
            if self.http is None:
                self.http = httpx.AsyncClient()
            voice = settings.abena_voice(language_id, self.voice)
            audio = base64.b64encode(await abena.synthesize(self.http, text, voice)).decode()
            mime = abena.MIME
        except Exception as error:
            log.warning("Speech service failed for a sentence, the browser will speak it: %s", error)
            audio = mime = None
        await self.send(type="audio", turn=turn, index=index, audio=audio, mime=mime)

    async def reply(self, turn: int, user_text: str) -> None:
        question = {"role": "user", "content": user_text}
        self.history.append(question)
        splitter = SentenceSplitter()
        spoken: list[str] = []
        audio_tasks: list[asyncio.Task] = []
        started = time.monotonic()
        language = self.language  # a change mid reply waits for the next reply
        extra = {"name": self.name} if self.name else {}  # only sent when set
        spoken_id = language.id  # the language the reply is really in, once Gemini says

        async def say(sentence: str) -> None:
            index = len(spoken)
            if index == 0:
                log.info("Turn %s: first sentence ready after %d ms", turn, (time.monotonic() - started) * 1000)
            has_audio = bool(settings.abena_voice(spoken_id, self.voice))
            await self.send(type="sentence", turn=turn, index=index, text=sentence, audio_expected=has_audio)
            spoken.append(sentence)
            if has_audio:
                # Start right away so sentences are prepared in parallel.
                # The browser plays them in order of their index.
                audio_tasks.append(asyncio.create_task(self.send_audio(turn, index, sentence, spoken_id)))

        try:
            await self.send(type="status", turn=turn, state="thinking")
            searched = False
            async for event in reply_events(self.history, language, **extra):
                kind = event["type"]
                if kind == "text":
                    for sentence in splitter.feed(event["text"]):
                        await say(sentence)
                elif kind == "language":
                    spoken_id = event["language"]
                    await self.send(type="language", turn=turn, language=event["language"])
                elif kind == "searching":
                    for sentence in splitter.flush():
                        await say(sentence)
                    await self.send(type="status", turn=turn, state="searching")
                    if not searched:  # fill the silence, once per reply
                        await say(language.filler)
                    searched = True
                elif kind == "search_done":
                    await self.send(type="status", turn=turn, state="thinking")
                elif kind == "search_failed":
                    log.warning("Web search failed on turn %s: %s", turn, event.get("reason"))
                    await self.send(type="search_failed", turn=turn)
                elif kind == "sources":
                    await self.send(type="sources", turn=turn, sources=event["sources"])
            for sentence in splitter.flush():
                await say(sentence)
            await asyncio.gather(*audio_tasks)
            await self.send(type="done", turn=turn)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("Reply failed on turn %s", turn)
            await self.send(type="error", turn=turn, message=error_text(error))
        finally:
            # Drop audio that is still being prepared, so none arrives after a barge in.
            for task in audio_tasks:
                task.cancel()
            await asyncio.gather(*audio_tasks, return_exceptions=True)
            # Remember only what was actually said, even if the reply was cut short.
            if spoken:
                self.history.append({"role": "assistant", "content": " ".join(spoken)})
            elif self.history and self.history[-1] is question:
                # Nothing was said (stopped or failed early). Forget the question too,
                # or the next reply would answer it as well.
                self.history.pop()

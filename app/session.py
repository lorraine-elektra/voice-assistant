"""One Session per WebSocket connection: history, the reply in progress, and barge in."""
import asyncio
import base64
import json
import logging
import time

import httpx
from fastapi import WebSocket

from app import abena, abena_voices, whisper
from app.brain import reply_events
from app.config import settings
from app.languages import DEFAULT, LANGUAGES, for_browser
from app.sentences import SentenceSplitter

log = logging.getLogger("voice")
ERROR_TEXT = "Sorry, something went wrong on my side. Please try again."
PHRASE_FAILED_TEXT = "I could not hear that. Please try again."


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
        self.http: httpx.AsyncClient | None = None  # reused for every Groq and Abena request
        self._send_lock = asyncio.Lock()

    async def send(self, **message) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        await self.send(
            type="ready", brain=settings.brain_mode, stt=settings.stt_mode, tts=settings.tts_mode,
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
            await self.cancel_reply()
            self.turn += 1
            self.reply_task = asyncio.create_task(self.reply(self.turn, text))
        elif kind == "stop":
            await self.cancel_reply()
        elif kind == "settings":
            language = LANGUAGES.get(message.get("language"))
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

    # ---------- speech to text: Groq Whisper, with Abena as a second opinion ----------

    async def hear_phrase(self, message: dict) -> None:
        """One recorded phrase from the browser. The words go back as a final transcript."""
        try:
            if settings.stt_mode != "whisper":
                raise RuntimeError("Whisper is not configured")
            audio = base64.b64decode(message["audio"])
            mime = str(message.get("mime") or "audio/wav")
            if self.http is None:
                self.http = httpx.AsyncClient()
            heard = await whisper.transcribe(self.http, audio, mime)
            text = heard.text
            if not heard.confident and settings.abena_mode:
                text = await self.second_opinion(audio, mime) or text
            await self.send(type="transcript", text=text, final=True)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.warning("Could not transcribe a phrase: %s", error)
            await self.send(type="error", message=PHRASE_FAILED_TEXT)

    async def second_opinion(self, audio: bytes, mime: str) -> str:
        """Whisper was guessing, which often means Twi. Ask Abena. "" if it cannot help."""
        language = self.language.id if self.language.id in abena.ASR_LANGUAGES else "tw"
        try:
            return await abena.transcribe(self.http, audio, mime, language)
        except Exception as error:
            log.warning("Abena could not give a second opinion: %s", error)
            return ""

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
        self.history.append({"role": "user", "content": user_text})
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
        except Exception:
            log.exception("Reply failed on turn %s", turn)
            await self.send(type="error", turn=turn, message=ERROR_TEXT)
        finally:
            # Drop audio that is still being prepared, so none arrives after a barge in.
            for task in audio_tasks:
                task.cancel()
            await asyncio.gather(*audio_tasks, return_exceptions=True)
            # Remember only what was actually said, even if the reply was cut short.
            if spoken:
                self.history.append({"role": "assistant", "content": " ".join(spoken)})

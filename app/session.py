"""One Session per WebSocket connection: history, the reply in progress, and barge in."""
import asyncio
import base64
import json
import logging
import time

import httpx
from fastapi import WebSocket

from app import tts
from app.brain import reply_events
from app.config import settings
from app.prompts import SEARCH_FILLER
from app.sentences import SentenceSplitter
from app.stt import DeepgramRelay

log = logging.getLogger("voice")
ERROR_TEXT = "Sorry, something went wrong on my side. Please try again."
STT_FAILED_TEXT = "The speech service is not available, so the browser will listen instead."


class Session:
    def __init__(self, websocket: WebSocket) -> None:
        self.ws = websocket
        self.history: list[dict] = []  # lives only as long as the connection
        self.turn = 0
        self.reply_task: asyncio.Task | None = None
        self.relay: DeepgramRelay | None = None
        self.http: httpx.AsyncClient | None = None  # reused for every ElevenLabs request
        self._send_lock = asyncio.Lock()

    async def send(self, **message) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        await self.send(
            type="ready", brain=settings.brain_mode, stt=settings.stt_mode, tts=settings.tts_mode
        )
        try:
            while True:
                frame = await self.ws.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                if frame.get("bytes") is not None:
                    if self.relay:
                        await self.relay.send_audio(frame["bytes"])
                elif frame.get("text") is not None:
                    await self.on_text_frame(frame["text"])
        finally:
            await self.cancel_reply(notify=False)
            await self.stop_listening()
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
        elif kind == "audio_start":
            await self.start_listening(message.get("sample_rate"))
        elif kind == "audio_stop":
            await self.stop_listening()
        elif kind == "latency":
            log.info(
                "Turn %s: %s ms from end of speech to first spoken word (web search: %s)",
                message.get("turn"), message.get("ms"), bool(message.get("searched")),
            )
        else:
            await self.send(type="error", message=f"Unknown message type: {kind}")

    # ---------- speech to text (Deepgram) ----------

    async def start_listening(self, sample_rate) -> None:
        await self.stop_listening()
        try:
            if settings.stt_mode != "deepgram":
                raise RuntimeError("Deepgram is not configured")
            relay = DeepgramRelay(self.on_transcript, self.on_stt_closed)
            await relay.start(int(sample_rate))
            self.relay = relay
        except Exception as error:
            log.warning("Could not start Deepgram: %s", error)
            await self.send(type="stt_failed", message=STT_FAILED_TEXT)

    async def stop_listening(self) -> None:
        relay, self.relay = self.relay, None
        if relay:
            await relay.close()

    async def on_transcript(self, text: str, final: bool) -> None:
        await self.send(type="transcript", text=text, final=final)

    async def on_stt_closed(self) -> None:
        self.relay = None
        await self.send(type="stt_failed", message=STT_FAILED_TEXT)

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

    async def send_audio(self, turn: int, index: int, text: str) -> None:
        """Turn one sentence into audio. On failure send null so the browser speaks it."""
        try:
            if self.http is None:
                self.http = httpx.AsyncClient()
            audio = base64.b64encode(await tts.synthesize(self.http, text)).decode()
        except Exception as error:
            log.warning("ElevenLabs failed for a sentence, the browser will speak it: %s", error)
            audio = None
        await self.send(type="audio", turn=turn, index=index, audio=audio)

    async def reply(self, turn: int, user_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        splitter = SentenceSplitter()
        spoken: list[str] = []
        audio_tasks: list[asyncio.Task] = []
        started = time.monotonic()

        async def say(sentence: str) -> None:
            index = len(spoken)
            if index == 0:
                log.info("Turn %s: first sentence ready after %d ms", turn, (time.monotonic() - started) * 1000)
            await self.send(type="sentence", turn=turn, index=index, text=sentence)
            spoken.append(sentence)
            if settings.tts_mode == "elevenlabs":
                # Start right away so sentences are prepared in parallel.
                # The browser plays them in order of their index.
                audio_tasks.append(asyncio.create_task(self.send_audio(turn, index, sentence)))

        try:
            await self.send(type="status", turn=turn, state="thinking")
            searched = False
            async for event in reply_events(self.history):
                kind = event["type"]
                if kind == "text":
                    for sentence in splitter.feed(event["text"]):
                        await say(sentence)
                elif kind == "searching":
                    for sentence in splitter.flush():
                        await say(sentence)
                    await self.send(type="status", turn=turn, state="searching")
                    if not searched:  # fill the silence, once per reply
                        await say(SEARCH_FILLER)
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

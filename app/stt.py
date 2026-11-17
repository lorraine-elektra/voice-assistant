"""Deepgram live speech to text. The browser sends audio to us, we pass it on to
Deepgram and pass the words back, so the key never leaves the backend.
Docs: https://developers.deepgram.com/reference/speech-to-text/listen-streaming
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from app.config import settings

log = logging.getLogger("voice")
API = "wss://api.deepgram.com/v1/listen"
KEEPALIVE_SECONDS = 4  # Deepgram hangs up after 10 seconds with no audio and no KeepAlive


def deepgram_url(sample_rate: int) -> str:
    return API + "?" + urlencode({
        "model": settings.deepgram_model,
        "encoding": "linear16",  # raw 16 bit audio, which is what the page sends
        "sample_rate": sample_rate,
        "channels": 1,
        "interim_results": "true",  # words while the user is still talking
        "smart_format": "true",
        "endpointing": 300,  # ms of silence that ends a phrase
        "utterance_end_ms": 1000,  # backup signal that the user has stopped
    })


class DeepgramRelay:
    """on_transcript(text, final) is awaited for every update from Deepgram.
    on_closed() is awaited if Deepgram drops the connection by itself."""

    def __init__(self, on_transcript: Callable[[str, bool], Awaitable], on_closed: Callable[[], Awaitable]):
        self.on_transcript = on_transcript
        self.on_closed = on_closed
        self.parts: list[str] = []  # finished pieces of the phrase being spoken
        self.tasks: list[asyncio.Task] = []
        self.ws = None

    async def start(self, sample_rate: int) -> None:
        headers = {"Authorization": f"Token {settings.deepgram_api_key}"}
        self.ws = await connect(deepgram_url(sample_rate), additional_headers=headers)
        self.tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._keepalive())]

    async def send_audio(self, chunk: bytes) -> None:
        if self.ws is not None:
            await self.ws.send(chunk)

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        if self.ws is not None:
            await self.ws.close()
            self.ws = None

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(KEEPALIVE_SECONDS)
            await self.ws.send(json.dumps({"type": "KeepAlive"}))

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                await self.handle(json.loads(raw))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Deepgram connection failed")
        # Deepgram hung up by itself. Tidy up, then tell the session.
        self.tasks[1].cancel()
        self.tasks, self.ws = [], None
        await self.on_closed()

    async def handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "UtteranceEnd":
            await self._finish_phrase()
        if kind != "Results":
            return
        text = message["channel"]["alternatives"][0]["transcript"].strip()
        if message.get("is_final"):
            if text:
                self.parts.append(text)
            if message.get("speech_final"):
                await self._finish_phrase()
        elif text:
            await self.on_transcript(" ".join(self.parts + [text]), False)

    async def _finish_phrase(self) -> None:
        if self.parts:
            phrase, self.parts = " ".join(self.parts), []
            await self.on_transcript(phrase, True)

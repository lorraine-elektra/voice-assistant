"""One Session per WebSocket connection: history, the reply in progress, and barge in."""
import asyncio
import json
import logging

from fastapi import WebSocket

from app.brain import reply_events
from app.config import settings
from app.sentences import SentenceSplitter

log = logging.getLogger("voice")
ERROR_TEXT = "Sorry, something went wrong on my side. Please try again."


class Session:
    def __init__(self, websocket: WebSocket) -> None:
        self.ws = websocket
        self.history: list[dict] = []  # lives only as long as the connection
        self.turn = 0
        self.reply_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()

    async def send(self, **message) -> None:
        async with self._send_lock:
            await self.ws.send_json(message)

    async def run(self) -> None:
        await self.send(type="ready", brain=settings.brain_mode)
        try:
            while True:
                frame = await self.ws.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                if frame.get("text") is not None:
                    await self.on_text_frame(frame["text"])
        finally:
            await self.cancel_reply(notify=False)

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
        else:
            await self.send(type="error", message=f"Unknown message type: {kind}")

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

    async def reply(self, turn: int, user_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        splitter = SentenceSplitter()
        spoken: list[str] = []

        async def say(sentence: str) -> None:
            await self.send(type="sentence", turn=turn, index=len(spoken), text=sentence)
            spoken.append(sentence)

        try:
            await self.send(type="status", turn=turn, state="thinking")
            async for event in reply_events(self.history):
                if event["type"] == "text":
                    for sentence in splitter.feed(event["text"]):
                        await say(sentence)
            for sentence in splitter.flush():
                await say(sentence)
            await self.send(type="done", turn=turn)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Reply failed on turn %s", turn)
            await self.send(type="error", turn=turn, message=ERROR_TEXT)
        finally:
            # Remember only what was actually said, even if the reply was cut short.
            if spoken:
                self.history.append({"role": "assistant", "content": " ".join(spoken)})

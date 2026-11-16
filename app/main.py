import logging

from fastapi import FastAPI, WebSocket

from app.session import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Voice Assistant")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket.accept()
    await Session(websocket).run()

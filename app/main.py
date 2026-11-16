import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.session import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Voice Assistant")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def page():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await websocket.accept()
    await Session(websocket).run()

import logging
from pathlib import Path
from urllib.parse import urlsplit

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


def from_our_page(websocket: WebSocket) -> bool:
    """Browsers say which page opened the socket. Only our own page may use the assistant,
    so another website cannot spend the owner's API quota. Tools that send no Origin are fine."""
    origin = websocket.headers.get("origin")
    return origin is None or urlsplit(origin).netloc == websocket.headers.get("host")


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    if not from_our_page(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await Session(websocket).run()

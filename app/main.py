from fastapi import FastAPI

app = FastAPI(title="Voice Assistant")


@app.get("/health")
def health():
    return {"status": "ok"}

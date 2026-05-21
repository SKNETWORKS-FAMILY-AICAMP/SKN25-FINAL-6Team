"""FastAPI endpoints for the chatbot service."""

from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(title="Chatbot API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

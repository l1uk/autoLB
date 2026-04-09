from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Autologbook Backend")


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

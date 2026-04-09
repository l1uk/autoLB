from fastapi import FastAPI


app = FastAPI(title="autologbook backend")


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

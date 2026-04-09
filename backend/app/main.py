from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.core.security import close_redis_client, generate_rsa_keypair, get_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    generate_rsa_keypair()
    await init_db()
    app.state.settings = settings
    app.state.redis = get_redis_client()
    yield
    await close_redis_client()
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="autologbook backend", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)

    @application.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()

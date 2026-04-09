from __future__ import annotations

import os

from celery import Celery


def create_celery_app() -> Celery:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    app = Celery(
        "autologbook",
        broker=redis_url,
        backend=redis_url,
    )
    app.conf.update(
        task_default_queue="default",
        task_ignore_result=False,
    )
    return app


celery_app = create_celery_app()
app = celery_app

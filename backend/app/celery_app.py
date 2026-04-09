from celery import Celery

from app.core.config import get_settings
from app.tasks import mark_offline_clients


celery_app = Celery("autologbook")
settings = get_settings()
celery_app.conf.broker_url = settings.redis_url
celery_app.conf.result_backend = settings.redis_url
celery_app.conf.beat_schedule = {
    "mark-offline-clients": {
        "task": "app.tasks.mark_offline_clients",
        "schedule": 60.0,
    }
}
celery_app.task(name="app.tasks.mark_offline_clients")(mark_offline_clients)

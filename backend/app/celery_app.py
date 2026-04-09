from celery import Celery


celery_app = Celery("autologbook")
celery_app.conf.broker_url = "redis://redis:6379/0"
celery_app.conf.result_backend = "redis://redis:6379/0"

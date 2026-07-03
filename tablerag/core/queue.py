"""Shared Celery app.

The API enqueues by task *name* only (`send_task`), so it never imports the
ingestion package; the worker (tablerag/ingestion/worker.py) imports the task
implementations and registers them on this same app.
"""

from celery import Celery

from tablerag.core.config import get_settings

TASK_PROCESS_DOCUMENT = "ingestion.process_document"


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery("tablerag", broker=settings.redis_url, backend=settings.redis_url)
    # acks_late + idempotent tasks: a worker killed mid-job gets the job
    # redelivered and reprocessing wipes the doc's previous elements first
    # (Phase 1 DoD: no duplicate elements after kill+retry).
    app.conf.task_acks_late = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.broker_connection_retry_on_startup = True
    return app


celery_app = create_celery()

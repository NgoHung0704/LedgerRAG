"""Celery worker entry point.

Run:  celery -A tablerag.ingestion.worker worker --loglevel=info
"""

from tablerag.core.logging import setup_logging
from tablerag.core.queue import celery_app
import tablerag.ingestion.tasks  # noqa: F401  (registers tasks on the app)

setup_logging()

app = celery_app

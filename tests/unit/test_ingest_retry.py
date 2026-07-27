"""Ingestion retry policy: a transient infra error (Qdrant/model timeout under
bulk-upload load) is retried with backoff, not turned into a permanent failure;
a genuinely bad document still fails fast."""

import httpx
from qdrant_client.http.exceptions import ResponseHandlingException

from tablerag.ingestion.extract import PdfError
from tablerag.ingestion.tasks import (
    MAX_INGEST_RETRIES,
    _is_transient,
    _retry_countdown,
)


def test_transient_errors_are_retried():
    # the exact failure the user hit: Qdrant REST timeout wrapped by the client
    assert _is_transient(ResponseHandlingException(httpx.ReadTimeout("timed out")))
    # model-side timeouts/connection drops share the treatment
    assert _is_transient(httpx.ReadTimeout("timed out"))
    assert _is_transient(httpx.ConnectError("connection refused"))


def test_permanent_errors_are_not_retried():
    # a broken PDF or a logic bug must fail fast, not spin the retry budget
    assert not _is_transient(PdfError("The PDF contains no pages."))
    assert not _is_transient(ValueError("bad state"))


def test_retry_countdown_backs_off_and_caps():
    seq = [_retry_countdown(i) for i in range(6)]
    assert seq[:4] == [5, 10, 20, 40]      # exponential
    assert seq[-1] == 60                    # capped
    assert all(a <= b for a, b in zip(seq, seq[1:]))  # monotonic
    assert MAX_INGEST_RETRIES == 3

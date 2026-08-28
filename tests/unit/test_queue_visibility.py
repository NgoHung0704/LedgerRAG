"""One document re-ingested every three hours, for a day.

`task_acks_late = True` is deliberate: a worker killed mid-job must get the job
back, and ingestion wipes a document's previous elements before rewriting them,
so a redelivery cannot duplicate anything. But acks_late means the ack lands
when the task FINISHES, and Redis redelivers anything unacknowledged after its
`visibility_timeout` — which defaults to one hour and was never configured.

A 24-page document measured 10 776 s. At the one-hour mark Redis decided the
worker had died and handed the job to it again; three hours later that copy
finished and the next was already waiting. The same task id looped from 18:28
to 06:26 the following morning, burning the GPU on work already done, and the
status flipped done → parsing → done → parsing so the interface showed
"parsing" whenever a reader happened to look.

    'acknowledged': False, 'redelivered': True

The two settings are each right and wrong together: acks_late REQUIRES a
visibility timeout longer than the longest task.
"""

from tablerag.core.queue import create_celery

# Measured on the box, 2026-08-27: one 24-page document, end to end.
# The point of writing it down is the test below — a timeout set under this
# reproduces the loop, and nobody should have to rediscover that.
OBSERVED_LONGEST_INGEST_SECONDS = 10_776


def test_the_visibility_timeout_is_configured_at_all():
    # unset means the Redis default of one hour, which is the bug
    options = create_celery().conf.broker_transport_options
    assert "visibility_timeout" in options


def test_it_leaves_real_headroom_over_the_longest_measured_ingest():
    timeout = create_celery().conf.broker_transport_options["visibility_timeout"]
    assert timeout > OBSERVED_LONGEST_INGEST_SECONDS, (
        "a timeout under the longest observed ingestion redelivers the job "
        "before it can finish, and the document re-ingests forever"
    )
    # a margin, not a hair: 10 800 (three hours) cleared the measurement by
    # twenty-four seconds and would loop on any document slightly larger
    assert timeout >= 2 * OBSERVED_LONGEST_INGEST_SECONDS


def test_late_acknowledgement_is_still_on():
    # the setting the timeout exists to support. Dropping it would "fix" the
    # loop by losing the job of any worker that dies mid-document instead.
    assert create_celery().conf.task_acks_late is True


def test_the_deployment_can_change_it_without_a_rebuild():
    from tablerag.core.config import Settings

    assert "ingest_visibility_timeout" in Settings.model_fields

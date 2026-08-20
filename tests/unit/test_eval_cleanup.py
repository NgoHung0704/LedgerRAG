"""An eval run must not leave its questions sitting in somebody's chat history.

Every question asked without a session_id mints a stored conversation — true of
the KB endpoint since Phase 1, and newly VISIBLE now that `--assistant` puts
them in the sidebar a reader actually looks at. A 39-question run left 39
threads behind, indistinguishable from real ones.

Cleanup runs AFTER the score is printed, which drives the whole design: it may
never raise, never abort, and never obscure the numbers the run exists to
produce. A failed delete is counted and reported, not thrown.
"""

import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, REPO / "tests" / "eval" / "qa" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qa = _load("run_eval_qa")


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeClient:
    """Records what was deleted. `fail_on` raises for that id, `status` maps an
    id to a status code."""

    def __init__(self, fail_on: str | None = None, status: dict | None = None):
        self.deleted: list[str] = []
        self.fail_on = fail_on
        self.status = status or {}

    def delete(self, url: str) -> FakeResponse:
        sid = url.rsplit("/", 1)[-1]
        self.deleted.append(sid)
        if sid == self.fail_on:
            raise RuntimeError("connection reset")
        return FakeResponse(self.status.get(sid, 204))


def test_each_conversation_the_run_created_is_removed():
    client = FakeClient()
    deleted, failed = qa.cleanup_conversations(client, ["s1", "s2", "s3"])
    assert (deleted, failed) == (3, 0)
    assert client.deleted == ["s1", "s2", "s3"]


def test_keeping_them_deletes_nothing_at_all():
    # --keep-conversations: the run is being inspected by hand
    client = FakeClient()
    deleted, failed = qa.cleanup_conversations(client, ["s1"], keep=True)
    assert (deleted, failed) == (0, 0)
    assert client.deleted == []


def test_a_session_reused_across_turns_is_deleted_once():
    # the follow-up harness threads one session through a whole conversation,
    # so the same id arrives once per graded turn
    client = FakeClient()
    deleted, _ = qa.cleanup_conversations(client, ["s1", "s1", "s2", "s1"])
    assert client.deleted == ["s1", "s2"]
    assert deleted == 2


def test_a_delete_that_raises_is_counted_not_thrown():
    # cleanup runs after the score is printed; an exception here would abort
    # the run and bury the numbers it exists to produce
    client = FakeClient(fail_on="s2")
    deleted, failed = qa.cleanup_conversations(client, ["s1", "s2", "s3"])
    assert (deleted, failed) == (2, 1)
    assert client.deleted == ["s1", "s2", "s3"], "one failure must not stop the rest"


def test_an_already_absent_conversation_counts_as_cleaned():
    # 404 means the thread is not there, which is the state we wanted
    client = FakeClient(status={"s2": 404})
    deleted, failed = qa.cleanup_conversations(client, ["s1", "s2"])
    assert (deleted, failed) == (2, 0)


def test_a_refusal_is_reported_rather_than_swallowed():
    client = FakeClient(status={"s1": 403})
    deleted, failed = qa.cleanup_conversations(client, ["s1"])
    assert (deleted, failed) == (0, 1)


def test_questions_that_never_got_a_session_are_skipped():
    # a question that errored out has no session to remove
    client = FakeClient()
    deleted, failed = qa.cleanup_conversations(client, [None, "", "s1"])
    assert client.deleted == ["s1"]
    assert (deleted, failed) == (1, 0)

"""The API key that stands in for one KB in the Dify-compatible External
Knowledge API (`/api/retrieval/{kb_id}/retrieval`).

Same shape as tests/unit/test_embed_token.py for the assistant embed token:
the key does not buy secrecy on a plain-http intranet deployment, it buys
revocation and an explicit opt-in per KB (SPEC constraint C1).
"""

import uuid

from tablerag.storage import repositories as repo


def _kb(s, config: dict):
    return repo.create_kb(s, name="HR", description="", config=config)


def test_a_key_finds_its_kb(db_session):
    kb = _kb(db_session, {"retrieval_key": "key_abc"})
    found = repo.get_kb_by_retrieval_key(db_session, "key_abc")
    assert found is not None and found.id == kb.id


def test_an_unknown_key_finds_nothing(db_session):
    _kb(db_session, {"retrieval_key": "key_abc"})
    assert repo.get_kb_by_retrieval_key(db_session, "key_zzz") is None


def test_a_revoked_key_finds_nothing(db_session):
    kb = _kb(db_session, {"retrieval_key": "key_abc"})
    kb.config = {}
    db_session.flush()
    assert repo.get_kb_by_retrieval_key(db_session, "key_abc") is None


def test_a_blank_key_matches_nothing_even_if_one_is_stored(db_session):
    _kb(db_session, {"retrieval_key": "   "})
    for probe in ("", "   ", "\t"):
        assert repo.get_kb_by_retrieval_key(db_session, probe) is None


def test_two_kbs_do_not_collide(db_session):
    a = _kb(db_session, {"retrieval_key": "key_a"})
    b = _kb(db_session, {"retrieval_key": "key_b"})
    assert repo.get_kb_by_retrieval_key(db_session, "key_a").id == a.id
    assert repo.get_kb_by_retrieval_key(db_session, "key_b").id == b.id
    assert uuid.UUID(str(b.id))


def test_a_minted_key_is_long_and_unguessable():
    import secrets

    a, b = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    assert a != b
    assert len(a) >= 24
    assert a == a.strip() and "/" not in a and "?" not in a and "#" not in a


def test_the_output_schema_carries_the_key():
    from tablerag.core.schemas import KBOut

    assert "retrieval_key" in KBOut.model_fields

"""The token that stands in for one assistant when another application hosts it.

It does not buy secrecy: `auth.mode` is `disabled` on the deployment box, so
everyone who can reach the API on the intranet is already an administrator of
it. It buys revocation, and it buys being able to switch authentication on later
without tearing out a deployed embed.
"""

import uuid

from tablerag.storage import repositories as repo


def _assistant(s, config: dict):
    return repo.create_assistant(s, name="HR", description="", instructions="",
                                 config=config)


def test_a_token_finds_its_assistant(db_session):
    a = _assistant(db_session, {"embed_token": "tok_abc"})
    found = repo.get_assistant_by_embed_token(db_session, "tok_abc")
    assert found is not None and found.id == a.id


def test_an_unknown_token_finds_nothing(db_session):
    _assistant(db_session, {"embed_token": "tok_abc"})
    assert repo.get_assistant_by_embed_token(db_session, "tok_zzz") is None


def test_a_revoked_token_finds_nothing(db_session):
    a = _assistant(db_session, {"embed_token": "tok_abc"})
    a.config = {}
    db_session.flush()
    assert repo.get_assistant_by_embed_token(db_session, "tok_abc") is None


def test_a_blank_token_matches_nothing_even_if_one_is_stored(db_session):
    # the escalation-contact lesson, in the one place where getting it wrong
    # would hand out an assistant to anyone sending an empty string
    _assistant(db_session, {"embed_token": "   "})
    for probe in ("", "   ", "\t"):
        assert repo.get_assistant_by_embed_token(db_session, probe) is None


def test_two_assistants_do_not_collide(db_session):
    a = _assistant(db_session, {"embed_token": "tok_a"})
    b = _assistant(db_session, {"embed_token": "tok_b"})
    assert repo.get_assistant_by_embed_token(db_session, "tok_a").id == a.id
    assert repo.get_assistant_by_embed_token(db_session, "tok_b").id == b.id
    assert uuid.UUID(str(b.id))


# --- minting happens on the server ------------------------------------------
# The plan first had the browser call crypto.randomUUID(). That function exists
# only in a secure context, and the box serves over plain http on an intranet
# name — so the button would have thrown, in production only.


def test_a_minted_token_is_long_and_unguessable():
    from tablerag.api.routes.assistants import mint_embed_token

    a, b = mint_embed_token(), mint_embed_token()
    assert a != b
    assert len(a) >= 24
    # url-safe: it travels in a path segment
    assert a == a.strip() and "/" not in a and "?" not in a and "#" not in a


def test_the_output_schema_carries_the_token_but_the_face_does_not():
    from tablerag.core.schemas import AssistantOut, EmbedFace

    assert "embed_token" in AssistantOut.model_fields
    # what another application is served must not include the credential that
    # reaches it, nor the knowledge bases behind it
    assert "embed_token" not in EmbedFace.model_fields
    assert "kb_ids" not in EmbedFace.model_fields

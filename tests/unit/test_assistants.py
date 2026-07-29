"""Assistants: a chat app with its own knowledge bases, prompt and threads.

The invariants worth pinning are the ownership ones — an assistant REFERENCES
knowledge bases (deleting one must not touch the corpus), and deleting an
assistant must not leave orphaned conversations or messages behind.
"""

import uuid

from tablerag.storage import repositories as repo
from tablerag.storage.orm import ChatMessage, ChatSession


def _kb(db_session, name="HR"):
    return repo.create_kb(db_session, name, f"{name} documents")


def test_create_with_kbs_and_read_back(db_session):
    a_kb, b_kb = _kb(db_session, "Accords"), _kb(db_session, "Glossaire")
    assistant = repo.create_assistant(
        db_session, "Assistant RH", "Répond aux questions RH",
        instructions="Cite les numéros d'article.",
        config={"opening_message": "Bonjour !"},
        kb_ids=[a_kb.id, b_kb.id])

    assert repo.get_assistant(db_session, assistant.id) is not None
    assert set(repo.assistant_kb_ids(db_session, assistant.id)) == {a_kb.id, b_kb.id}
    assert assistant.instructions == "Cite les numéros d'article."
    assert assistant.config["opening_message"] == "Bonjour !"
    assert [x.id for x in repo.list_assistants(db_session)] == [assistant.id]


def test_set_kbs_replaces_the_attached_set(db_session):
    one, two, three = _kb(db_session, "A"), _kb(db_session, "B"), _kb(db_session, "C")
    assistant = repo.create_assistant(db_session, "X", kb_ids=[one.id, two.id])

    repo.set_assistant_kbs(db_session, assistant.id, [two.id, three.id])
    assert set(repo.assistant_kb_ids(db_session, assistant.id)) == {two.id, three.id}

    # detaching everything is legitimate (an assistant with no context yet)
    repo.set_assistant_kbs(db_session, assistant.id, [])
    assert repo.assistant_kb_ids(db_session, assistant.id) == []


def test_unknown_kb_ids_are_ignored_not_fatal(db_session):
    kb = _kb(db_session)
    assistant = repo.create_assistant(db_session, "X",
                                      kb_ids=[kb.id, uuid.uuid4()])
    assert repo.assistant_kb_ids(db_session, assistant.id) == [kb.id]


def test_deleting_a_kb_detaches_it_but_keeps_the_assistant(db_session):
    keep, gone = _kb(db_session, "Keep"), _kb(db_session, "Gone")
    assistant = repo.create_assistant(db_session, "X", kb_ids=[keep.id, gone.id])

    repo.delete_kb(db_session, gone.id)
    db_session.flush()

    assert repo.get_assistant(db_session, assistant.id) is not None
    assert repo.assistant_kb_ids(db_session, assistant.id) == [keep.id]


def test_deleting_an_assistant_removes_its_conversations_and_messages(db_session):
    kb = _kb(db_session)
    assistant = repo.create_assistant(db_session, "X", kb_ids=[kb.id])
    session = repo.get_or_create_session(db_session, kb.id, None)
    repo.link_conversation(db_session, assistant.id, session.id, "Salaires")
    repo.add_message(db_session, session.id, "user", "Bonjour")

    assert repo.delete_assistant(db_session, assistant.id) is True
    db_session.flush()

    assert repo.get_assistant(db_session, assistant.id) is None
    assert repo.list_conversations(db_session, assistant.id) == []
    assert db_session.query(ChatSession).count() == 0
    assert db_session.query(ChatMessage).count() == 0
    # the knowledge base is untouched — assistants reference, never own
    assert repo.get_kb(db_session, kb.id) is not None


def test_conversation_link_list_rename_delete(db_session):
    kb = _kb(db_session)
    assistant = repo.create_assistant(db_session, "X", kb_ids=[kb.id])
    first = repo.get_or_create_session(db_session, kb.id, None)
    second = repo.get_or_create_session(db_session, kb.id, None)
    repo.link_conversation(db_session, assistant.id, first.id, "Première question")
    repo.link_conversation(db_session, assistant.id, second.id, "Deuxième")

    titles = {c["session_id"]: c["title"]
              for c in repo.list_conversations(db_session, assistant.id)}
    assert titles == {first.id: "Première question", second.id: "Deuxième"}

    # linking again is idempotent (it only touches updated_at)
    repo.link_conversation(db_session, assistant.id, first.id, "ignored")
    assert len(repo.list_conversations(db_session, assistant.id)) == 2

    repo.rename_conversation(db_session, first.id, "Salaires 2024")
    assert any(c["title"] == "Salaires 2024"
               for c in repo.list_conversations(db_session, assistant.id))

    assert repo.delete_conversation(db_session, second.id) is True
    db_session.flush()
    assert [c["session_id"]
            for c in repo.list_conversations(db_session, assistant.id)] == [first.id]
    assert repo.delete_conversation(db_session, uuid.uuid4()) is False


def test_conversations_are_scoped_to_their_assistant(db_session):
    kb = _kb(db_session)
    a = repo.create_assistant(db_session, "A", kb_ids=[kb.id])
    b = repo.create_assistant(db_session, "B", kb_ids=[kb.id])
    sa = repo.get_or_create_session(db_session, kb.id, None)
    sb = repo.get_or_create_session(db_session, kb.id, None)
    repo.link_conversation(db_session, a.id, sa.id, "for A")
    repo.link_conversation(db_session, b.id, sb.id, "for B")

    assert [c["title"] for c in repo.list_conversations(db_session, a.id)] == ["for A"]
    assert [c["title"] for c in repo.list_conversations(db_session, b.id)] == ["for B"]


MINE = [
    ("Accords", "accords d'entreprise"),
    ("Glossaire", "définitions de la classification"),
]


async def test_routing_is_confined_to_the_assistants_kbs(monkeypatch):
    """The whole point of an assistant: a question can never be answered from a
    knowledge base it does not use. Routing is scoped through the LLMRouter's
    injectable fetcher, and still degrades to ALL OF ITS OWN KBs, never none."""
    from tablerag.query.pipeline import QueryContext
    from tablerag.query.steps.router import KBRef, LLMRouter

    mine = [KBRef(uuid.uuid4(), name, desc) for name, desc in MINE]

    async def only_mine():
        return mine

    class Chat:
        async def chat(self, messages, stream=True, temperature=None, options=None):
            # the router prompt only ever lists the assistant's own KBs
            assert "Accords" in messages[1].content
            assert "Glossaire" in messages[1].content
            yield "[2]"

    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: Chat())
    ctx = QueryContext(kb_id=mine[0].id, question="une définition ?")
    await LLMRouter(list_kbs_fn=only_mine).run(ctx)
    assert ctx.routed_kb_ids == [mine[1].id]

    class Boom:
        async def chat(self, *a, **k):
            raise RuntimeError("model down")
            yield  # pragma: no cover

    monkeypatch.setattr("tablerag.models.registry.get_provider",
                        lambda role: Boom())
    ctx = QueryContext(kb_id=mine[0].id, question="?")
    await LLMRouter(list_kbs_fn=only_mine).run(ctx)
    assert ctx.routed_kb_ids == [kb.id for kb in mine]  # its own, never none


def test_session_messages_replay_with_citations_and_feedback(db_session):
    """Reopening a thread must render exactly as it streamed."""
    kb = _kb(db_session)
    session = repo.get_or_create_session(db_session, kb.id, None)
    repo.add_message(db_session, session.id, "user", "Quel salaire ?")
    answer = repo.add_message(
        db_session, session.id, "assistant", "34 900 € [1]",
        citations=[{"index": 1, "filename": "Avenant.pdf", "page": 3}],
        verification={"enabled": True, "status": "ok"})
    repo.set_feedback(db_session, answer.id, 1)

    replay = repo.get_session_messages(db_session, session.id)
    # order is load-bearing: both rows are written in ONE transaction, and the
    # PK is a random uuid — without strictly increasing timestamps the answer
    # could replay before its question (it did, before message_timestamp())
    assert [m["role"] for m in replay] == ["user", "assistant"]
    assert replay[1]["citations"][0]["filename"] == "Avenant.pdf"
    assert replay[1]["verification"]["status"] == "ok"
    assert replay[1]["feedback"] == 1
    assert replay[0]["feedback"] == 0

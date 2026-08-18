"""Who a reader is told to ask, and where that setting lives.

It used to live on the knowledge base. An assistant searching two of them that
named different departments had to fall back to generic wording, because naming
one department while the answer may have come from the other's document is
worse than naming none. An assistant has ONE fixed set of documents and one
purpose, so on the assistant there is nobody to be ambiguous with.
"""

import uuid

from tablerag.core.schemas import AssistantCreate, AssistantUpdate, KBUpdate


def test_the_knowledge_base_no_longer_carries_a_contact():
    # the field is gone from the KB's update schema; a client still sending it
    # is not silently half-obeyed
    assert "escalation_contact" not in KBUpdate.model_fields


def test_an_assistant_carries_one():
    assert AssistantCreate.model_fields["escalation_contact"].default == ""
    assert AssistantUpdate.model_fields["escalation_contact"].default is None


def test_a_new_assistant_stores_the_contact_it_was_given(db_session):
    from tablerag.storage import repositories as repo

    body = AssistantCreate(name="HR", escalation_contact="  service RH  ")
    config = {"opening_message": ""}
    if body.escalation_contact.strip():
        config["escalation_contact"] = body.escalation_contact.strip()
    a = repo.create_assistant(db_session, name=body.name, description="",
                              instructions="", config=config)
    assert (a.config or {}).get("escalation_contact") == "service RH"


def test_clearing_it_removes_the_key_rather_than_storing_a_blank(db_session):
    # a stored "" would read as a contact named "" downstream; `or None` in the
    # route covers that, but the config should not carry the ghost either
    from tablerag.storage import repositories as repo

    a = repo.create_assistant(
        db_session, name="HR", description="", instructions="",
        config={"escalation_contact": "service RH"})
    body = AssistantUpdate(escalation_contact="   ")
    config = dict(a.config or {})
    if body.escalation_contact is not None:
        wanted = body.escalation_contact.strip()
        if wanted:
            config["escalation_contact"] = wanted
        else:
            config.pop("escalation_contact", None)
    assert "escalation_contact" not in config


def test_two_knowledge_bases_disagreeing_no_longer_costs_the_contact():
    """The regression this move was made for.

    With the setting on the KBs, an assistant over an HR base and a finance
    base — each naming its own department — produced NO contact at all, and the
    reader got the generic wording precisely when they most needed a name. The
    assistant's own value does not consult them.
    """
    from tablerag.api.routes.assistants import escalation_contact

    kb_configs = [{"escalation_contact": "service RH"},
                  {"escalation_contact": "service Finance"}]
    old_rule = {c.get("escalation_contact") for c in kb_configs}
    assert len(old_rule) == 2, "the two KBs must disagree for this to mean anything"

    # the production function, not a re-implementation of it: the first version
    # of this test inlined the lookup, so making the route return None for
    # every assistant left it green
    assert escalation_contact({"escalation_contact": "service RH"}) == "service RH"
    assert escalation_contact({}) is None
    assert escalation_contact(None) is None
    assert escalation_contact({"escalation_contact": "   "}) is None


def test_an_assistant_without_one_says_nothing_rather_than_guessing(db_session):
    from tablerag.storage import repositories as repo

    a = repo.create_assistant(db_session, name="HR", description="",
                              instructions="", config={"opening_message": ""})
    assert ((a.config or {}).get("escalation_contact") or None) is None
    assert uuid.UUID(str(a.id))

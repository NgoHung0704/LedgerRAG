"""The chat system prompt is a correctness contract (copy numbers exactly,
answer only from sources, refuse honestly). Operator instructions are ADDITIVE:
they may shape tone/focus but must never displace that core. These tests pin
that the core is always present and always precedes the operator block."""

from tablerag.query.steps.generate import (
    INSTRUCTIONS_HEADER,
    SYSTEM_PROMPT,
    build_system_prompt,
)


def test_no_extra_is_the_core_verbatim():
    assert build_system_prompt("") == SYSTEM_PROMPT
    assert build_system_prompt("   \n ") == SYSTEM_PROMPT
    assert build_system_prompt() == SYSTEM_PROMPT


def test_extra_is_appended_after_the_core():
    extra = "Cite the article number. Answer in a formal register."
    p = build_system_prompt(extra)
    # the whole safety core comes first, unchanged
    assert p.startswith(SYSTEM_PROMPT)
    assert INSTRUCTIONS_HEADER in p
    assert p.rstrip().endswith(extra)
    # a load-bearing rule is still there, and precedes the operator block
    assert "EXACTLY" in p
    assert p.index("EXACTLY") < p.index("Additional instructions")


def test_operator_block_is_framed_as_subordinate():
    p = build_system_prompt("Toujours répondre en trois phrases maximum.")
    # the appended header reminds the model the rules above win
    lowered = p.lower()
    assert "must not override" in lowered
    assert "only from the numbered sources" in lowered


# --- identity ---------------------------------------------------------------

def test_identity_is_absent_unless_the_operator_sets_one():
    """No identity configured -> the answering prompt stays byte-identical to
    the measured configuration, so the eval gates cannot move."""
    assert build_system_prompt("", "") == SYSTEM_PROMPT
    assert build_system_prompt("", "   ") == SYSTEM_PROMPT


def test_identity_is_prepended_before_the_rules():
    p = build_system_prompt("", "l'assistant RH du CETIAT")
    assert p.startswith("You are l'assistant RH du CETIAT")
    assert SYSTEM_PROMPT in p
    assert p.index("You are") < p.index("LANGUAGE")


def test_identity_and_instructions_stack_in_order():
    p = build_system_prompt("Cite les numéros d'article.", "l'assistant RH")
    assert p.index("l'assistant RH") < p.index("LANGUAGE") \
        < p.index("Additional instructions") < p.index("Cite les numéros")


# --- the conversational prompt ("qui es-tu ?") -------------------------------

def test_smalltalk_prompt_falls_back_to_the_built_in_identity():
    from tablerag.query.steps.generate import DEFAULT_IDENTITY
    from tablerag.query.steps.smalltalk import build_smalltalk_prompt

    p = build_smalltalk_prompt("")
    assert DEFAULT_IDENTITY in p
    assert p.startswith("You are ")


def test_smalltalk_prompt_uses_the_operator_identity_and_guidance():
    from tablerag.query.steps.smalltalk import build_smalltalk_prompt

    p = build_smalltalk_prompt("l'assistant RH du CETIAT", "Tutoie l'utilisateur.")
    assert "l'assistant RH du CETIAT" in p
    assert p.rstrip().endswith("Tutoie l'utilisateur.")
    # it must still refuse to invent document facts
    assert "never state any fact" in p

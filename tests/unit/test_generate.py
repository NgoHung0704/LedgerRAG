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

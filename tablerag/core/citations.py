"""Reading citation markers back out of an answer, and what they oblige us to say.

A figure description is a model's READING of a picture, not text printed on the
page. A low-confidence table was parsed unreliably by our own admission. Both
are presented to the reader in the same voice as a number quoted straight off a
grid, and nothing distinguishes them once the answer is on screen.

The caution is a FIELD, not a sentence. The obvious alternative — a rule in
SYSTEM_PROMPT asking the model to warn the reader — was rejected twice over: a
14B model omits such a sentence unpredictably, and every edit to that prompt
shifts the measured configuration for EVERY query, including the ones with no
picture in them. As a field it fires whenever the condition holds, and the
answer text does not change by one byte.

Judged on what the model ACTUALLY cited, not on everything it was shown: an
answer that quotes one clean table should not be hedged because some unrelated
chart happened to be in the context. The exception is an answer citing nothing
at all — that is the case where we know least about where it came from, so it
is judged on everything.
"""

from __future__ import annotations

import re

from tablerag.core.schemas import Caution, Citation

# a marker is a bracketed number and nothing else. "[voir annexe]" is prose.
_MARKER = re.compile(r"\[(\d{1,3})\]")


def cited_indices(answer: str) -> set[int]:
    return {int(m) for m in _MARKER.findall(answer or "")}


def caution_for(answer: str, citations: list[Citation],
                contact: str | None,
                verification: dict | None = None,
                confidence_threshold: float = 0.9) -> Caution | None:
    """Whether this answer rests on something a human should check.

    `verification` is the Verify step's result, and it carries the most concrete
    thing this system knows about a shaky answer: a number printed in the answer
    that matched no number in any retrieved source. It was rendered as its own
    badge while this field — the one that says "check the original, or ask the
    contact" — stayed silent about it.

    Read only when the check actually RAN. A knowledge base with verification
    switched off must not come out looking safer than one where it ran and
    passed; silence there means nothing was measured, not that nothing is wrong.
    """
    used = cited_indices(answer)
    relevant = [c for c in citations if not used or c.index in used]
    reasons: list[str] = []
    if (verification or {}).get("enabled") and (verification or {}).get("unverified"):
        reasons.append("unverified_numbers")
    if any(c.from_figure for c in relevant):
        reasons.append("figure_reading")
    if any(c.needs_review for c in relevant):
        reasons.append("needs_review")
    if any(c.confidence is not None and c.confidence < confidence_threshold
           for c in relevant):
        reasons.append("low_confidence")
    if not reasons:
        return None
    return Caution(reasons=reasons, contact=contact)

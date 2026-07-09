"""Answer-number verification (SPEC Phase 4) — the last link of "never a
number without a source".

After the LLM answers, every number in the answer is extracted (locale-aware,
reusing core/numbers.py) and checked against the numbers that were in the
retrieved context:

- matches a source number (after normalization + rounding tolerance) -> verified
- equals a simple arithmetic combination (sum / difference / ratio) of a few
  source numbers -> computed (the LLM legitimately did the math; SPEC's
  whitelist so we don't warn on totals/percentages it derived)
- otherwise -> unverified, and the answer carries a warning next to it

Best-effort by design: it errs toward warning rather than silent error
(SPEC §0.3). Value-only matching can't catch a hallucinated number that
happens to coincide with an unrelated source value — the real guarantee
remains the cited source, always shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tablerag.core.numbers import parse_number

# a number token: optional sign/paren/currency, digits with locale separators,
# optional percent / trailing currency
_NUMBER_RE = re.compile(
    r"[-−–+(]?\s?[€$£¥]?\s?\d[\d    .,']*\d\s?%?\s?[€$£¥]?\)?"
    r"|(?<![\w.])\d+\s?%?",
)

_REL_TOL = 1e-3
_ABS_TOL = 0.5
_MAX_SOURCE_VALUES = 80     # cap combinatorics
_MAX_TRIPLE_VALUES = 25


@dataclass
class NumberCheck:
    raw: str
    value: float
    status: str  # 'verified' | 'computed' | 'unverified'


@dataclass
class VerificationResult:
    enabled: bool = True
    status: str = "ok"  # 'ok' | 'warnings'
    numbers: list[NumberCheck] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "status": self.status,
            "numbers": [{"raw": n.raw, "value": n.value, "status": n.status}
                        for n in self.numbers],
            "unverified": self.unverified,
        }


def extract_numbers(text: str, locale: str | None) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group().strip()
        parsed = parse_number(raw, locale)
        if parsed is not None:
            out.append((raw, parsed.value))
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(_ABS_TOL, _REL_TOL * max(abs(a), abs(b)))


def _derivable(target: float, values: list[float]) -> bool:
    """target == a simple combination of <= 3 source values (SPEC whitelist)."""
    for i, a in enumerate(values):
        for b in values[i + 1:]:
            for candidate in (a + b, abs(a - b), a * b):
                if _close(target, candidate):
                    return True
            for x, y in ((a, b), (b, a)):
                if y and _close(target, x / y):
                    return True
                if y and _close(target, 100 * x / y):  # percentage share
                    return True
    triples = values[:_MAX_TRIPLE_VALUES]
    for i, a in enumerate(triples):
        for j, b in enumerate(triples[i + 1:], i + 1):
            for c in triples[j + 1:]:
                if _close(target, a + b + c):
                    return True
    return False


def verify_answer(answer: str, source_texts: list[str],
                  locale: str | None) -> VerificationResult:
    source_values: list[float] = []
    seen: set[float] = set()
    for text in source_texts:
        for _, value in extract_numbers(text, locale):
            key = round(value, 2)
            if key not in seen:
                seen.add(key)
                source_values.append(value)
    source_values = source_values[:_MAX_SOURCE_VALUES]

    result = VerificationResult()
    for raw, value in extract_numbers(answer, locale):
        if any(_close(value, s) for s in source_values):
            status = "verified"
        elif _derivable(value, source_values):
            status = "computed"
        else:
            status = "unverified"
            result.unverified.append(raw)
        result.numbers.append(NumberCheck(raw=raw, value=value, status=status))

    result.status = "warnings" if result.unverified else "ok"
    return result

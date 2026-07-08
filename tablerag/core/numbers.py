"""Locale-aware number normalization (SPEC Phase 2, constraint C2).

Pure functions, no I/O. The declared locale (KB/document level) always wins;
inference only happens when no locale is given, is deliberately conservative,
and marks its result `ambiguous` when the string genuinely can't be decided
("1,234" alone could be 1234 or 1.234). Raw strings are never modified —
callers keep `raw_values` untouched (principle: never overwrite the source).

Conventions (documented per spec):
- "12,5 %" -> value 12.5, unit "%"  (percentages keep their percent scale)
- "7 462 639 EUR" / "... €" -> value 7462639, unit "EUR"
- Parentheses mean negative: "(1 234)" -> -1234
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACE_RE = re.compile(r"\s+")  # \s covers U+00A0 / U+202F / U+2009 in py3
_MINUS_CHARS = "-−–"  # hyphen-minus, true minus, en-dash

CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY"}
CURRENCY_CODES = {"EUR", "USD", "GBP", "CHF", "JPY", "CAD"}

# locale -> (grouping separator, decimal separator)
# fr groups with (non-breaking) spaces; de/es/it/pt group with dots; en with commas
_LOCALE_SEPS: dict[str, tuple[str, str]] = {
    "en": (",", "."),
    "fr": (" ", ","),
    "de": (".", ","),
    "es": (".", ","),
    "it": (".", ","),
    "pt": (".", ","),
}

SUPPORTED_LOCALES = frozenset(_LOCALE_SEPS)


@dataclass(frozen=True)
class ParsedNumber:
    value: float
    unit: str | None = None  # "%" or an ISO currency code
    ambiguous: bool = False  # locale had to be guessed and the guess is unsafe


def _normalize_spaces(s: str) -> str:
    s = "".join(" " if unicodedata.category(c) == "Zs" else c for c in s)
    return _SPACE_RE.sub(" ", s).strip()


def _strip_sign_and_unit(s: str) -> tuple[str, bool, str | None]:
    """Peel off sign, %, currency symbol/code. Returns (core, negative, unit)."""
    negative = False
    unit: str | None = None

    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    if s and s[0] in _MINUS_CHARS:
        negative = True
        s = s[1:].strip()
    elif s and s[0] == "+":
        s = s[1:].strip()

    if s.endswith("%"):
        unit = "%"
        s = s[:-1].strip()

    for symbol, code in CURRENCY_SYMBOLS.items():
        if s.startswith(symbol):
            unit = unit or code
            s = s[len(symbol):].strip()
        elif s.endswith(symbol):
            unit = unit or code
            s = s[:-len(symbol)].strip()

    tokens = s.split(" ")
    if tokens and tokens[-1].upper() in CURRENCY_CODES:
        unit = unit or tokens[-1].upper()
        s = " ".join(tokens[:-1])

    # sign may sit inside, revealed after the unit was peeled ("€-5") —
    # but never strip a second sign ("--5" must stay invalid)
    if s and s[0] in _MINUS_CHARS and not negative:
        negative = True
        s = s[1:].strip()

    return s.strip(), negative, unit


def _digits_only(core: str, group: str, dec: str) -> str | None:
    """Validate and reduce `core` (no sign/unit) to a python float literal
    using the given separators. Returns None when the string doesn't fit."""
    int_part, sep, frac = core.partition(dec)
    int_part, frac = int_part.strip(), frac.strip()

    if group == " ":
        groups = int_part.split(" ")
    else:
        if " " in int_part:  # spaces are only legal as fr-style grouping
            return None
        groups = int_part.split(group)

    if len(groups) > 1:
        # strict grouping: 1-3 leading digits, then groups of exactly 3
        if (not all(g.isdigit() and g for g in groups)
                or any(len(g) != 3 for g in groups[1:])
                or not (1 <= len(groups[0]) <= 3)):
            return None
    digits = "".join(groups)
    if not digits.isdigit():
        return None
    if sep and not frac:  # trailing decimal separator: "1,"
        return None
    if frac:
        if not frac.isdigit():
            return None
        return f"{digits}.{frac}"
    return digits


def parse_number(raw: str, locale: str | None = None) -> ParsedNumber | None:
    """Parse one printed number. `locale` should come from KB/document config;
    pass None only when genuinely unknown (inference is conservative)."""
    if raw is None:
        return None
    s = _normalize_spaces(str(raw))
    if not s:
        return None
    core, negative, unit = _strip_sign_and_unit(s)
    if not core or not any(ch.isdigit() for ch in core):
        return None

    if locale is not None:
        if locale not in _LOCALE_SEPS:
            raise ValueError(f"unsupported locale {locale!r} "
                             f"(supported: {sorted(SUPPORTED_LOCALES)})")
        group, dec = _LOCALE_SEPS[locale]
        literal = _digits_only(core, group, dec)
        if literal is None:
            return None
        value = float(literal)
        return ParsedNumber(-value if negative else value, unit, ambiguous=False)

    # ---- no declared locale: conservative inference ----
    has_comma, has_dot, has_space = "," in core, "." in core, " " in core
    ambiguous = False
    if has_space and not has_dot:
        literal = _digits_only(core, " ", ",")           # "7 462 639(,50)"
    elif has_comma and has_dot:
        # the LAST separator is the decimal one
        if core.rfind(",") > core.rfind("."):
            literal = _digits_only(core, ".", ",")       # "1.234,56" (de)
        else:
            literal = _digits_only(core, ",", ".")       # "1,234.56" (en)
    elif has_comma:
        frac = core.rsplit(",", 1)[1]
        if core.count(",") == 1 and len(frac) == 3:
            literal = _digits_only(core, ",", ".")       # "1,234" -> grouping...
            ambiguous = literal is not None              # ...but could be 1.234
        elif core.count(",") > 1:
            literal = _digits_only(core, ",", ".")       # "1,234,567"
        else:
            literal = _digits_only(core, " ", ",")       # "1,5" -> decimal
    elif has_dot:
        frac = core.rsplit(".", 1)[1]
        if core.count(".") == 1 and len(frac) == 3:
            literal = _digits_only(core, ".", ",")       # "1.234" -> grouping...
            ambiguous = literal is not None              # ...but could be 1.234
        elif core.count(".") > 1:
            literal = _digits_only(core, ".", ",")       # "1.234.567"
        else:
            literal = _digits_only(core, ",", ".")       # "1.5" -> decimal
    else:
        literal = core if core.isdigit() else None

    if literal is None:
        return None
    value = float(literal)
    return ParsedNumber(-value if negative else value, unit, ambiguous=ambiguous)

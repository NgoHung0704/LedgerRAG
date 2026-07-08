"""core/numbers.py — Phase 2 DoD: >= 20 cases per target locale (FR/DE/EN),
covering negatives, %, thousands by space/dot/comma, and U+202F."""

import pytest

from tablerag.core.numbers import ParsedNumber, parse_number

NNBSP = " "
NBSP = " "

FR_CASES = [
    ("7 462 639", 7462639.0, None),
    (f"7{NNBSP}462{NNBSP}639", 7462639.0, None),          # narrow no-break space
    (f"7{NBSP}462{NBSP}639", 7462639.0, None),            # no-break space
    ("7 462 639 €", 7462639.0, "EUR"),
    (f"7{NNBSP}462{NNBSP}639{NNBSP}€", 7462639.0, "EUR"),
    ("1 234,56", 1234.56, None),
    ("1 234,56 €", 1234.56, "EUR"),
    ("1234,5", 1234.5, None),
    ("0,5", 0.5, None),
    ("12,5 %", 12.5, "%"),
    ("12,5%", 12.5, "%"),
    ("-12,5 %", -12.5, "%"),
    ("- 1 234", -1234.0, None),
    ("−1 234", -1234.0, None),                            # U+2212 true minus
    ("(1 234)", -1234.0, None),
    ("(1 234,56 €)", -1234.56, "EUR"),
    ("426", 426.0, None),
    ("1 250,00 €", 1250.0, "EUR"),
    ("287,2 %", 287.2, "%"),
    ("+42", 42.0, None),
    ("13 040 620", 13040620.0, None),
    ("999", 999.0, None),
    ("1 234 EUR", 1234.0, "EUR"),
]

DE_CASES = [
    ("7.462.639", 7462639.0, None),
    ("7.462.639,50", 7462639.5, None),
    ("7.462.639,50 €", 7462639.5, "EUR"),
    ("1.234,56", 1234.56, None),
    ("1.234", 1234.0, None),
    ("12.840", 12840.0, None),
    ("986.420,75", 986420.75, None),
    ("0,5", 0.5, None),
    ("1234,5", 1234.5, None),
    ("12,5 %", 12.5, "%"),
    ("-12,5 %", -12.5, "%"),
    ("(1.234)", -1234.0, None),
    ("−1.234,50", -1234.5, None),
    ("3.207.911,25 €", 3207911.25, "EUR"),
    ("24.310.480,50", 24310480.5, None),
    ("42", 42.0, None),
    ("+3.100", 3100.0, None),
    ("1.234 EUR", 1234.0, "EUR"),
    ("999", 999.0, None),
    ("100,00", 100.0, None),
    ("5.104.880,00", 5104880.0, None),
]

EN_CASES = [
    ("7,462,639", 7462639.0, None),
    ("7,462,639.50", 7462639.5, None),
    ("$7,462,639.50", 7462639.5, "USD"),
    ("€1,254,300", 1254300.0, "EUR"),
    ("£999", 999.0, "GBP"),
    ("1,234.56", 1234.56, None),
    ("1,234", 1234.0, None),
    ("0.5", 0.5, None),
    ("1234.5", 1234.5, None),
    ("12.5%", 12.5, "%"),
    ("12.5 %", 12.5, "%"),
    ("-12.5%", -12.5, "%"),
    ("(1,234)", -1234.0, None),
    ("(1,234.56)", -1234.56, None),
    ("-1,234.56", -1234.56, None),
    ("42", 42.0, None),
    ("+42", 42.0, None),
    ("8,420", 8420.0, None),
    ("2,107,880", 2107880.0, None),
    ("1,240.5", 1240.5, None),
    ("1,234 USD", 1234.0, "USD"),
    ("105", 105.0, None),
]

ES_CASES = [
    ("1.534.210,40", 1534210.4, None),
    ("1.534.210,40 €", 1534210.4, "EUR"),
    ("1.240", 1240.0, None),
    ("12,5 %", 12.5, "%"),
    ("-987,6", -987.6, None),
]


@pytest.mark.parametrize("raw,value,unit", FR_CASES)
def test_fr(raw, value, unit):
    parsed = parse_number(raw, "fr")
    assert parsed == ParsedNumber(value, unit, ambiguous=False)


@pytest.mark.parametrize("raw,value,unit", DE_CASES)
def test_de(raw, value, unit):
    parsed = parse_number(raw, "de")
    assert parsed == ParsedNumber(value, unit, ambiguous=False)


@pytest.mark.parametrize("raw,value,unit", EN_CASES)
def test_en(raw, value, unit):
    parsed = parse_number(raw, "en")
    assert parsed == ParsedNumber(value, unit, ambiguous=False)


@pytest.mark.parametrize("raw,value,unit", ES_CASES)
def test_es(raw, value, unit):
    parsed = parse_number(raw, "es")
    assert parsed == ParsedNumber(value, unit, ambiguous=False)


# ---- declared locale is strict: wrong-locale strings are rejected ----

@pytest.mark.parametrize("raw,locale", [
    ("7.462.639", "fr"),       # dot-grouping is not French
    ("1,234.56", "de"),        # en shape under de locale
    ("1.234,56", "en"),        # de shape under en locale
    ("1 234", "en"),           # space grouping is not English
    ("12,34,56", "en"),        # broken grouping
    ("1,23", "en"),            # 2-digit "group"
    ("abc", "fr"),
    ("", "fr"),
    ("--5", "fr"),
    ("1,", "fr"),
])
def test_rejects_wrong_shape(raw, locale):
    assert parse_number(raw, locale) is None


def test_unsupported_locale_raises():
    with pytest.raises(ValueError):
        parse_number("1", "xx")


# ---- inference without declared locale: conservative + flags ambiguity ----

@pytest.mark.parametrize("raw,value,ambiguous", [
    ("7 462 639", 7462639.0, False),       # spaces: unambiguous fr-style
    ("7 462 639,50", 7462639.5, False),
    ("1.234,56", 1234.56, False),          # both seps: last one is decimal
    ("1,234.56", 1234.56, False),
    ("1.234.567", 1234567.0, False),       # repeated: grouping
    ("1,234,567", 1234567.0, False),
    ("1,5", 1.5, False),                   # not a 3-digit tail: decimal
    ("1.5", 1.5, False),
    ("1,234", 1234.0, True),               # genuinely ambiguous
    ("1.234", 1234.0, True),
    ("426", 426.0, False),
])
def test_inference(raw, value, ambiguous):
    parsed = parse_number(raw)
    assert parsed is not None
    assert parsed.value == value
    assert parsed.ambiguous is ambiguous


def test_raw_string_is_never_needed_back():
    """Callers keep raw_values; parse_number must not mutate its input."""
    raw = "7 462 639 €"
    parse_number(raw, "fr")
    assert raw == "7 462 639 €"

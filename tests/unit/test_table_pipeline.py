"""Phase 2 table sub-pipeline units: contract validation, classifier,
simple-path record building, text_repr, VLM fallback via fake provider."""

import pytest

from tablerag.ingestion.layout import table_grid_is_complex
from tablerag.ingestion.table_pipeline import (
    TableResult,
    build_text_repr,
    parse_table_region,
    records_from_grid,
)
from tablerag.models.base import Msg, TableCtx
from tablerag.models.table_parsing import (
    TableContractError,
    parse_response,
    run_table_parse,
)

GOOD_RESPONSE = """\
```html
<table><tr><th>Pays</th><th>CA</th></tr><tr><td>Maroc</td><td>5 240 880</td></tr></table>
```

```json
{"records": [
  {"dimensions": {"pays": "Maroc"},
   "metrics": {"ca": 5240880},
   "raw_values": {"ca": "5 240 880"}}
]}
```
"""


# ---------------------------------------------------------- contract

def test_parse_response_valid():
    html, records = parse_response(GOOD_RESPONSE)
    assert html.startswith("<table>")
    assert records[0]["metrics"]["ca"] == 5240880


@pytest.mark.parametrize("bad,fragment", [
    ("no blocks at all", "missing ```html"),
    ("```html\n<table></table>\n```", "missing ```json"),
    ("```html\n<t/>\n```\n```json\n{broken\n```", "not valid JSON"),
    ("```html\n<t/>\n```\n```json\n{\"records\": []}\n```", ">= 1 record"),
    ('```html\n<t/>\n```\n```json\n{"records": [{"dimensions": {}, '
     '"metrics": {"m": "1 234"}, "raw_values": {}}]}\n```', "JSON number"),
])
def test_parse_response_contract_errors(bad, fragment):
    with pytest.raises(TableContractError, match=fragment.replace("(", "\\(")):
        parse_response(bad)


async def test_run_table_parse_retries_then_succeeds():
    calls = []

    async def chat(messages: list[Msg], stream=True, temperature=None):
        calls.append(messages)
        text = "garbage" if len(calls) == 1 else GOOD_RESPONSE
        yield text

    result = await run_table_parse(chat, b"png", TableCtx(locale_hint="fr"))
    assert result.error is None
    assert len(result.records) == 1
    assert len(calls) == 2
    # the retry carries the concrete error back to the model
    assert "missing ```html" in calls[1][-1].content


async def test_run_table_parse_honest_failure_after_retry():
    async def chat(messages, stream=True, temperature=None):
        yield "still garbage"

    result = await run_table_parse(chat, b"png", TableCtx())
    assert result.error is not None
    assert result.records == []


# ---------------------------------------------------------- classifier

def test_classifier_flat_grid_is_simple():
    grid = [["Pays", "CA", "Volume"],
            ["Maroc", "5 240 880", "301"],
            ["France", "12 480 300", "712"]]
    assert table_grid_is_complex(grid) is False


@pytest.mark.parametrize("grid", [
    None,
    [["only header"]],
    [["A", "B"], ["x"]],                       # ragged rows
    [["A", None], ["x", "1"]],                 # header gap -> merged levels
    [["A", "B"], [None, None], [None, "1"]],   # many empties -> merged cells
])
def test_classifier_anomalies_go_to_vlm(grid):
    assert table_grid_is_complex(grid) is True


# ---------------------------------------------------------- simple path

def test_records_from_grid_fr():
    grid = [["Catégorie", "Jours", "Prime"],
            ["Cadre", "25", "1 250,00 €"],
            ["Employé", "28", "1 730,25 €"]]
    records = records_from_grid(grid, "fr")
    assert len(records) == 2
    first = records[0]
    assert first["dimensions"] == {"catégorie": "Cadre"}
    assert first["metrics"] == {"jours": 25.0, "prime": 1250.0}
    assert first["raw_values"]["prime"] == "1 250,00 €"  # raw kept verbatim
    assert "Cadre" in first["text_repr"] and "1 250,00 €" in first["text_repr"]


def test_records_from_grid_keeps_at_least_one_dimension():
    grid = [["A", "B"], ["1", "2"], ["3", "4"]]  # all columns numeric
    records = records_from_grid(grid, "en")
    assert all(rec["dimensions"] for rec in records)


def test_build_text_repr_prefers_raw_strings():
    repr_ = build_text_repr({"pays": "Maroc"}, {"ca": 5240880.0},
                            {"ca": "5 240 880"})
    assert repr_ == "Maroc | ca: 5 240 880"


# ---------------------------------------------------------- region dispatch

async def test_parse_table_region_simple_path_no_model_call(monkeypatch):
    monkeypatch.setattr(
        "tablerag.ingestion.table_pipeline.get_provider",
        lambda role: pytest.fail("simple path must not touch the VLM"))
    grid = [["Pays", "CA"], ["Maroc", "5 240 880"]]
    result = await parse_table_region(b"png", grid, is_complex=False, locale="fr")
    assert isinstance(result, TableResult)
    assert result.parse_strategy == "simple_parser"
    assert result.records[0]["metrics"]["ca"] == 5240880.0


async def test_parse_table_region_vlm_honest_failure(monkeypatch):
    class FailingParser:
        async def parse_table(self, image, ctx):
            from tablerag.models.base import TableParse
            return TableParse(html="<table></table>", records=[],
                              error="contract violation after retry: x")

    monkeypatch.setattr("tablerag.ingestion.table_pipeline.get_provider",
                        lambda role: FailingParser())
    result = await parse_table_region(b"png", None, is_complex=True, locale="fr")
    assert result.needs_review is True
    assert result.records == []
    assert result.html == "<table></table>"  # salvaged html survives

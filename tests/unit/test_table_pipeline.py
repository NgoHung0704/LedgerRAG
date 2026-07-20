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

    async def chat(messages: list[Msg], stream=True, temperature=None, options=None):
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
    async def chat(messages, stream=True, temperature=None, options=None):
        yield "still garbage"

    result = await run_table_parse(chat, b"png", TableCtx())
    assert result.error is not None
    assert result.records == []


async def test_run_table_parse_passes_large_context_options():
    """Regression guard: the production path must send num_ctx (the missing
    option that dropped production eval ~10 points below the spike)."""
    seen = {}

    async def chat(messages, stream=True, temperature=None, options=None):
        seen.update(options or {})
        yield GOOD_RESPONSE

    await run_table_parse(chat, b"png", TableCtx(locale_hint="fr"))
    assert seen.get("num_ctx", 0) >= 8192
    assert seen.get("temperature") == 0.0
    assert "seed" in seen


def test_get_double_read_provider_none_by_default(monkeypatch):
    from tablerag.core.config import get_settings
    from tablerag.models import registry

    get_settings.cache_clear()
    monkeypatch.delenv("LEDGERRAG_DOUBLE_READ_MODEL_NAME", raising=False)
    assert registry.get_double_read_provider() is None


def test_get_double_read_provider_builds_cross_model(monkeypatch):
    from tablerag.core.config import get_settings
    from tablerag.models import registry

    get_settings.cache_clear()
    monkeypatch.setattr(registry, "_overrides", lambda: {})  # no DB in unit tests
    monkeypatch.setenv("LEDGERRAG_MODELS__PARSER__PROVIDER", "ollama")
    monkeypatch.setenv("LEDGERRAG_MODELS__PARSER__BASE_URL", "http://gpu:11435")
    monkeypatch.setenv("LEDGERRAG_MODELS__PARSER__MODEL_NAME", "qwen3-vl:8b-instruct")
    monkeypatch.setenv("LEDGERRAG_DOUBLE_READ_MODEL_NAME", "minicpm-v:latest")
    try:
        provider = registry.get_double_read_provider()
        assert provider is not None
        assert provider.model == "minicpm-v:latest"
        assert provider.base_url == "http://gpu:11435"  # reuses parser base_url
    finally:
        get_settings.cache_clear()
        registry.reset_providers()


async def test_double_read_variant_shifts_seed_and_temperature():
    """Phase 3: the second read must be an independent opinion."""
    seen = {}

    async def chat(messages, stream=True, temperature=None, options=None):
        seen.update(options or {})
        yield GOOD_RESPONSE

    await run_table_parse(chat, b"png", TableCtx(locale_hint="fr"))
    base_seed = seen["seed"]
    await run_table_parse(chat, b"png",
                          TableCtx(locale_hint="fr", read_variant=1))
    assert seen["seed"] == base_seed + 1
    assert seen["temperature"] > 0.0


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
    assert repr_ == "pays: Maroc | ca: 5 240 880"


def test_build_text_repr_names_every_dimension():
    """A row must say which column each value came from: unnamed values sent
    the model looking for the 'cotation' in a different table (run 6)."""
    repr_ = build_text_repr(
        {"Cotations": "37 à 39", "Classes d'emplois": "11",
         "Groupes d'emplois": "F", "Emplois CETIAT": "Acheteur(se)"}, {}, {})
    assert repr_.startswith("Cotations: 37 à 39")
    assert "Groupes d'emplois: F" in repr_


def test_build_text_repr_keeps_bare_value_for_unnamed_columns():
    # blank/positional headers are real (CETIAT's salary column has none)
    assert build_text_repr({"": "21 700", "2": "x"}, {}, {}) == "21 700 | x"


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


def test_format_grid_hint_forward_fills_merged_label():
    from tablerag.models.table_parsing import format_grid_hint

    grid = [["Groupe", "Classe", "Emploi"],
            ["H", "15", "Directeur"],
            [None, "16", ""]]  # merged 'H' spanning down -> was blank
    hint = format_grid_hint(grid)
    assert "Groupe | Classe | Emploi" in hint
    assert "H | 15 | Directeur" in hint
    assert "H | 16 |" in hint  # merged 'H' propagated down; Emploi stays blank


def test_forward_fill_grid_reconstructs_cetiat_rowspans():
    from tablerag.models.table_parsing import forward_fill_grid

    # Cotation | Classe | Groupe | Emplois — H covers 15-16, I covers 17-18,
    # and Emplois is legitimately empty on the continuation rows
    grid = [
        ["Cotation", "Classe", "Groupe", "Emplois"],
        ["49", "15", "H", "Directeur(trice)"],
        ["52", "16", None, None],
        ["55", "17", "I", "Adjoint(e)"],
        ["58", "18", "", ""],
    ]
    out = forward_fill_grid(grid)
    assert [row[2] for row in out[1:]] == ["H", "H", "I", "I"]  # group filled
    # guardrails: long text (Emplois) NOT filled, numbers NOT propagated
    assert out[2][3] in (None, "")   # Emplois continuation stays empty
    assert out[4][3] == ""
    assert [row[0] for row in out[1:]] == ["49", "52", "55", "58"]  # untouched


def test_forward_fill_grid_never_fills_leading_blanks():
    from tablerag.models.table_parsing import forward_fill_grid

    grid = [[None, "x"], ["H", "y"], [None, "z"]]
    out = forward_fill_grid(grid)
    assert out[0][0] in (None, "")   # leading blank stays
    assert out[2][0] == "H"          # blank under a label is filled


def test_forward_fill_first_column_propagates_long_domain_labels():
    """Glossaire case: 'Fabrication' spans many rows in the leftmost column."""
    from tablerag.models.table_parsing import forward_fill_grid

    grid = [
        ["Domaines professionnels", "Techniques", "Activités"],
        ["Fabrication", "Chaudronnerie", "Assemblage"],
        [None, "Usinage-outillage", "Réglage"],
        [None, "Production sidérurgique", "Chargement"],
        ["Maintenance", "Mécanique", "Diagnostic"],
        [None, "Energétique", "Dépannage"],
    ]
    out = forward_fill_grid(grid)
    assert [row[0] for row in out[1:]] == [
        "Fabrication", "Fabrication", "Fabrication",
        "Maintenance", "Maintenance"]
    # header never propagates
    assert out[0][0] == "Domaines professionnels"


def test_forward_fill_header_row_never_propagates():
    from tablerag.models.table_parsing import forward_fill_grid

    grid = [["Groupe", "Val"], [None, "1"], ["H", "2"], [None, "3"]]
    out = forward_fill_grid(grid)
    assert out[1][0] in (None, "")   # blank right under the header stays blank
    assert out[3][0] == "H"


def test_forward_fill_other_columns_still_short_labels_only():
    from tablerag.models.table_parsing import forward_fill_grid

    grid = [["A", "Emploi"],
            ["1", "Directeur(trice)"],
            ["2", None]]  # genuinely empty job cell (col != 0)
    out = forward_fill_grid(grid)
    assert out[2][1] in (None, "")  # long text not propagated outside col 0


async def test_vlm_path_display_html_comes_from_grid_not_model(monkeypatch):
    """Text-layer: the geometry-derived grid is authoritative for display —
    the model's (possibly misaligned) html must not be used."""
    class SloppyParser:
        async def parse_table(self, image, ctx):
            from tablerag.models.base import RecordParse, TableParse
            return TableParse(
                html="<table><tr><td>totally</td><td>wrong</td></tr></table>",
                records=[RecordParse(dimensions={"d": "Fabrication"},
                                     metrics={"n": 1}, raw_values={"n": "1"})])

    monkeypatch.setattr("tablerag.ingestion.table_pipeline.get_provider",
                        lambda role: SloppyParser())
    grid = [["Domaine", "Technique"],
            ["Fabrication", "Chaudronnerie"],
            [None, "Usinage"]]
    result = await parse_table_region(b"png", grid, is_complex=True, locale="fr")
    assert "totally" not in result.html          # model html discarded
    assert 'rowspan="2">Fabrication' in result.html  # filled + re-merged
    assert result.records                        # records still from the VLM


def test_forward_fill_grid_does_not_propagate_numbers():
    from tablerag.models.table_parsing import forward_fill_grid

    grid = [["Total", "100"], ["", ""]]  # blank metric must NOT become 100
    out = forward_fill_grid(grid)
    assert out[1][1] in (None, "")
    assert out[1][0] == "Total" or out[1][0] in (None, "")  # 'Total' is 5 chars > max


def test_format_grid_hint_flattens_in_cell_newlines():
    from tablerag.models.table_parsing import format_grid_hint

    grid = [["Domaine", "Techniques"],
            ["Admin", "Comptabilité\nContrôle de gestion\nAudit"]]
    hint = format_grid_hint(grid)
    assert "Admin | Comptabilité; Contrôle de gestion; Audit" in hint
    assert len(hint.splitlines()) == 2  # one line per grid row, always


def test_grid_display_html_keeps_in_cell_newlines():
    from tablerag.ingestion.table_pipeline import grid_display_html

    grid = [["Domaine", "Techniques"],
            ["Admin", "Comptabilité\nContrôle de gestion\nFinances\nAudit"]]
    html = grid_display_html(grid)
    assert ("Comptabilité<br>Contrôle de gestion<br>Finances<br>Audit"
            in html)


def test_format_grid_hint_none_for_empty():
    from tablerag.models.table_parsing import format_grid_hint

    assert format_grid_hint(None) is None
    assert format_grid_hint([]) is None
    assert format_grid_hint([[None, ""], ["", None]]) is None


def test_build_user_prompt_injects_grid_hint():
    from tablerag.models.table_parsing import build_user_prompt

    base = build_user_prompt("fr")
    with_hint = build_user_prompt("fr", "H | 15 | Directeur")
    assert "EXTRACTED CELL TEXT" not in base
    assert "EXTRACTED CELL TEXT" in with_hint
    assert "H | 15 | Directeur" in with_hint
    assert "take the merge structure from the image" in with_hint


async def test_grid_hint_flows_to_vlm_on_complex_text_layer_table(monkeypatch):
    """Glossaire case: multi-level header (blank th) keeps the table on the
    VLM path, and the VLM prompt is grounded in the extracted values. (A
    single-header grid no longer reaches the VLM at all — see the
    deterministic grid path tests.)"""
    seen = {}

    class CapturingParser:
        async def parse_table(self, image, ctx):
            from tablerag.models.base import TableParse
            seen["grid_hint"] = ctx.grid_hint
            return TableParse(html="<table></table>", records=[], error="x")

    monkeypatch.setattr("tablerag.ingestion.table_pipeline.get_provider",
                        lambda role: CapturingParser())
    grid = [["Groupe", "Cotation", None], ["H", "49", "52"]]
    await parse_table_region(b"png", grid, is_complex=True, locale="fr")
    assert seen["grid_hint"] is not None
    assert "H | 49" in seen["grid_hint"]


def test_summary_prompt_forces_declared_language():
    from tablerag.ingestion.table_pipeline import build_summary_prompt

    prompt = build_summary_prompt("<table></table>", "fr")
    assert "in French ONLY" in prompt
    assert "never mix languages" in prompt


def test_summary_prompt_without_locale_still_forbids_mixing():
    from tablerag.ingestion.table_pipeline import build_summary_prompt

    prompt = build_summary_prompt("<table></table>", None)
    assert "dominant language of the table content ONLY" in prompt
    assert "never mix languages" in prompt


def test_ensure_min_width_upscales_small_images():
    import io

    from PIL import Image

    from tablerag.ingestion.imaging import ensure_min_width

    buf = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buf, format="PNG")
    out = ensure_min_width(buf.getvalue(), min_width=1400)
    with Image.open(io.BytesIO(out)) as img:
        assert img.width == 1400
        assert img.height == 700  # aspect ratio preserved


def test_ensure_min_width_leaves_large_images_untouched():
    import io

    from PIL import Image

    from tablerag.ingestion.imaging import ensure_min_width

    buf = io.BytesIO()
    Image.new("RGB", (2000, 900), "white").save(buf, format="PNG")
    data = buf.getvalue()
    assert ensure_min_width(data, min_width=1400) is data


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


def test_parser_prompt_carries_no_rule_4():
    """RULE 4 ('cover every column' / 'row-attribute column') was added to fix
    the dropped 'Emplois CETIAT' column and MEASURED OUT on the box: baseline
    prompt 79.9%, wide variant 75.1% (wide_en_technical 24/24 -> 4/24), narrow
    variant 75.7% (twolevel_fr_effectifs 8/12 -> 0/12). Every rewording made a
    different table collapse to zero — the record-column gap must be solved
    outside the parser prompt. This test pins the revert."""
    from tablerag.models.table_parsing import build_user_prompt

    prompt = build_user_prompt("fr")
    assert "RULE 4" not in prompt
    assert "row-attribute" not in prompt
    assert "Cover every column" not in prompt


# --- duplicate-dimension contract (eval-tables diagnostics, 2026-07-20) -----

DUPED_RESPONSE = """\
```html
<table><tr><th>Region</th><th>2023</th><th>2024</th></tr>\
<tr><td>DACH</td><td>24 310 480,5</td><td>26 905 320,75</td></tr></table>
```

```json
{"records": [
  {"dimensions": {"region": "DACH", "land": "Deutschland"},
   "metrics": {"umsatz_eur": 24310480.5}, "raw_values": {"umsatz_eur": "24 310 480,5"}},
  {"dimensions": {"region": "DACH", "land": "Deutschland"},
   "metrics": {"umsatz_eur": 26905320.75}, "raw_values": {"umsatz_eur": "26 905 320,75"}}
]}
```
"""


def test_duplicate_dimensions_violate_the_contract():
    """pivot_de_umsatz's exact failure shape: values perfect, year level
    dropped, so two records share {region, land} and nothing tells them
    apart — 0/16 despite correct numbers, presented confidently."""
    with pytest.raises(TableContractError, match="IDENTICAL dimensions"):
        parse_response(DUPED_RESPONSE)


def test_duplicate_error_names_the_offending_dims():
    try:
        parse_response(DUPED_RESPONSE)
    except TableContractError as e:
        assert "DACH" in str(e)            # the model is told WHICH rows
        assert "header level" in str(e)    # and WHAT to add
    else:
        pytest.fail("expected TableContractError")


def test_distinct_dimensions_still_pass():
    html, records = parse_response(GOOD_RESPONSE)
    assert len(records) == 1


def test_same_dims_different_order_is_still_a_duplicate():
    resp = DUPED_RESPONSE.replace(
        '{"region": "DACH", "land": "Deutschland"},\n   "metrics": {"umsatz_eur": 26905320.75}',
        '{"land": "Deutschland", "region": "DACH"},\n   "metrics": {"umsatz_eur": 26905320.75}')
    with pytest.raises(TableContractError, match="IDENTICAL dimensions"):
        parse_response(resp)


async def test_retry_recovers_from_duplicate_dimensions():
    """The retry must carry the duplicate diagnosis to the model — that is the
    whole mechanism: enforcement at validation time, not exhortation."""
    calls = []
    fixed = DUPED_RESPONSE.replace(
        '{"dimensions": {"region": "DACH", "land": "Deutschland"},\n   "metrics": {"umsatz_eur": 26905320.75}',
        '{"dimensions": {"region": "DACH", "land": "Deutschland", "jahr": "2024"},\n   "metrics": {"umsatz_eur": 26905320.75}')

    async def chat(messages, stream=True, temperature=None, options=None):
        calls.append(messages)
        yield DUPED_RESPONSE if len(calls) == 1 else fixed

    result = await run_table_parse(chat, b"png", TableCtx(locale_hint="de"))
    assert result.error is None
    assert len(calls) == 2
    assert "IDENTICAL dimensions" in calls[1][-1].content


async def test_persistent_duplicates_fail_honestly():
    async def chat(messages, stream=True, temperature=None, options=None):
        yield DUPED_RESPONSE

    result = await run_table_parse(chat, b"png", TableCtx())
    assert result.error is not None and "IDENTICAL" in result.error
    assert result.records == []
    assert result.html  # salvage kept for the LOW CONFIDENCE path


# ------------------------------ deterministic grid path (run 7 root cause)

CETIAT_GRID = [
    ["Cotations", "Classes\nd’emplois", "Groupes\nd’emplois", "Emplois CETIAT"],
    ["19 à 21", "5", "C", "Assistant(e) Commercial(e)\nGestionnaire Magasin"],
    ["22 à 24", "6", None, "Comptable"],
    ["37 à 39", "11", "F", "Acheteur(se)\nAdministrateur(trice) informatique"],
    ["40 à 42", "12", None, "Ingénieur(e) Commercial(e)"],
]


def test_cetiat_shaped_grid_is_derivable():
    from tablerag.ingestion.table_pipeline import grid_records_are_derivable

    assert grid_records_are_derivable(CETIAT_GRID)


def test_underivable_grids_stay_on_the_vlm_path():
    from tablerag.ingestion.table_pipeline import grid_records_are_derivable

    # blank in the header row = stacked multi-level headers (Glossaire)
    assert not grid_records_are_derivable(
        [["Domaines", "Techniques", None, "Activités"], ["a", "b", "c", "d"]])
    assert not grid_records_are_derivable(None)
    assert not grid_records_are_derivable([["only header"]])
    # a data row wider than the header cannot be aligned mechanically
    assert not grid_records_are_derivable([["A", "B"], ["x", "y", "z"]])


async def test_derivable_complex_grid_never_calls_the_vlm(monkeypatch):
    """Run 7 root cause: VLM records for CETIAT dropped the Emplois column and
    the unstable second read kept the table LOW CONFIDENCE, which the answer
    prompt honours by refusing its numbers. A single-header text-layer grid
    needs no model: records come from the grid, confidence is earned."""
    monkeypatch.setattr(
        "tablerag.ingestion.table_pipeline.get_provider",
        lambda role: pytest.fail("derivable grid must not touch the VLM"))

    result = await parse_table_region(b"png", CETIAT_GRID, True, "fr")

    assert result.parse_strategy == "grid"
    assert result.error is None and not result.needs_review
    by_class = {r["raw_values"].get("classes_d_emplois"): r
                for r in result.records}
    ach = by_class["11"]
    assert "Acheteur(se)" in ach["dimensions"]["emplois_cetiat"]
    assert ach["dimensions"]["cotations"] == "37 à 39"
    assert ach["dimensions"]["groupes_d_emplois"] == "F"
    # merged group label forward-filled onto the spanned sibling row
    assert by_class["12"]["dimensions"]["groupes_d_emplois"] == "F"
    # multi-line job list is one searchable line
    assert " / " in ach["dimensions"]["emplois_cetiat"]
    # searchable by job title AND by column name (both were impossible before)
    assert "Comptable" in by_class["6"]["text_repr"]
    assert "cotations: 22 à 24" in by_class["6"]["text_repr"].lower()

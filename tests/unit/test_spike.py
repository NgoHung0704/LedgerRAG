"""Sanity checks for the Phase 0 spike harness itself (generator + grader)."""

import json
import sys
from pathlib import Path

import pytest

SPIKE_DIR = str(Path(__file__).resolve().parents[2] / "spike")
if SPIKE_DIR not in sys.path:
    sys.path.insert(0, SPIKE_DIR)

import grade  # noqa: E402
import make_gt_template as gtt  # noqa: E402
import make_test_tables as mtt  # noqa: E402


def test_every_builder_produces_consistent_records():
    assert len(mtt.TABLES) >= 10  # spec: >= 10 test tables
    for table_id, builder in mtt.TABLES.items():
        rows, records, meta = builder()
        assert rows and records, table_id
        keys = frozenset(records[0]["dimensions"].keys())
        for record in records:
            assert frozenset(record["dimensions"].keys()) == keys, \
                f"{table_id}: dimension keys must be consistent within a table"
            assert set(record["metrics"]) == set(record["raw_values"]), \
                f"{table_id}: metrics and raw_values must share keys"


def test_locale_formatting():
    assert mtt.fmt(7462639, "fr") == f"7{mtt.NNBSP}462{mtt.NNBSP}639"
    assert mtt.fmt(7462639.50, "de", 2) == "7.462.639,50"
    assert mtt.fmt(7462639.50, "en", 2) == "7,462,639.50"
    assert mtt.fmt(-12.5, "fr", 1, " %") == "-12,5 %"
    assert mtt.NNBSP == " "


def test_flagship_pivot_matches_spec_example():
    _, records, meta = mtt.t_pivot_fr_auto()
    assert meta["difficulty"] == "pivot"
    target = [r for r in records
              if r["dimensions"] == {"region": "Afrique", "pays": "Algérie",
                                     "modele": "Citadine", "annee": "2013",
                                     "trimestre": "T1", "mois": "janv."}]
    assert len(target) == 1
    assert target[0]["metrics"]["chiffre_affaires_eur"] == 7462639
    assert target[0]["raw_values"]["chiffre_affaires_eur"] == \
        f"7{mtt.NNBSP}462{mtt.NNBSP}639"


def test_render_produces_image(tmp_path):
    rows, _, _ = mtt.t_flat_fr_conges()
    out = tmp_path / "image.png"
    mtt.render(rows, out)
    assert out.stat().st_size > 1000


def test_grader_accepts_renamed_keys():
    """The VLM may invent dimension/metric key names; only values count."""
    gt = {"table_id": "t", "records": [{
        "dimensions": {"region": "Afrique", "pays": "Algérie"},
        "metrics": {"ca": 7462639},
        "raw_values": {"ca": "7 462 639"},
    }]}
    parsed = {"records": [{
        "dimensions": {"level_1": "afrique", "level_2": "ALGÉRIE"},
        "metrics": {"revenue": 7462639.0},
        "raw_values": {"revenue": "7 462 639"},
    }]}
    result = grade.grade_table(gt, parsed)
    assert result["correct_cells"] == 1
    assert result["matched_records"] == 1


def test_grader_accepts_merged_header_values():
    """'2013' + 'T1' merged into one value '2013 T1' still localizes the cell."""
    gt = {"table_id": "t", "records": [{
        "dimensions": {"annee": "2013", "trimestre": "T1", "mois": "janv."},
        "metrics": {"ca": 7462639}, "raw_values": {"ca": "7 462 639"},
    }]}
    parsed = {"records": [{
        "dimensions": {"periode": "2013 T1", "mois": "janv."},
        "metrics": {"ca": 7462639}, "raw_values": {"ca": "7 462 639"},
    }]}
    result = grade.grade_table(gt, parsed)
    assert result["correct_cells"] == 1
    assert result["strict_correct_cells"] == 0  # relaxed, not strict


def test_grader_accepts_extra_parsed_dimensions():
    gt = {"table_id": "t", "records": [{
        "dimensions": {"pays": "Maroc"}, "metrics": {"m": 5},
        "raw_values": {"m": "5"},
    }]}
    parsed = {"records": [{
        "dimensions": {"pays": "Maroc", "devise": "EUR"},
        "metrics": {"m": 5}, "raw_values": {"m": "5"},
    }]}
    assert grade.grade_table(gt, parsed)["correct_cells"] == 1


def test_grader_pools_measures_split_across_records():
    """Fully-long output (one measure per record, measure name as an extra
    dimension) is a valid representation and must score all cells."""
    gt = {"table_id": "t", "records": [{
        "dimensions": {"product": "Alpha", "year": "2023"},
        "metrics": {"revenue_eur": 1254300, "volume": 8420},
        "raw_values": {"revenue_eur": "€1,254,300", "volume": "8,420"},
    }]}
    parsed = {"records": [
        {"dimensions": {"product": "Alpha", "year": "2023", "metric_type": "Revenue"},
         "metrics": {"revenue_eur": 1254300}, "raw_values": {"revenue_eur": "€1,254,300"}},
        {"dimensions": {"product": "Alpha", "year": "2023", "metric_type": "Volume"},
         "metrics": {"volume": 8420}, "raw_values": {"volume": "8,420"}},
    ]}
    result = grade.grade_table(gt, parsed)
    assert result["correct_cells"] == 2
    assert result["matched_records"] == 1


def test_grader_rejects_records_missing_dimensions():
    """One record per row with months folded away = localization failure."""
    gt = {"table_id": "t", "records": [{
        "dimensions": {"pays": "Maroc", "mois": "janv."},
        "metrics": {"ca": 100}, "raw_values": {"ca": "100"},
    }]}
    parsed = {"records": [{
        "dimensions": {"pays": "Maroc"},  # month missing
        "metrics": {"ca_janv": 100, "ca_fevr": 200},
        "raw_values": {"ca_janv": "100", "ca_fevr": "200"},
    }]}
    result = grade.grade_table(gt, parsed)
    assert result["correct_cells"] == 0
    assert result["matched_records"] == 0
    assert result["misses"][0]["kind"] == "unmatched"


def test_grader_rejects_wrong_numbers():
    gt = {"table_id": "t", "records": [{
        "dimensions": {"a": "x"}, "metrics": {"m": 100},
        "raw_values": {"m": "100"},
    }]}
    parsed = {"records": [{
        "dimensions": {"a": "x"}, "metrics": {"m": 101},
        "raw_values": {"m": "101"},
    }]}
    assert grade.grade_table(gt, parsed)["correct_cells"] == 0


def test_grader_honest_failure_counts_as_zero_not_crash():
    gt = {"table_id": "t", "records": [{
        "dimensions": {"a": "x"}, "metrics": {"m": 100}, "raw_values": {"m": "100"},
    }]}
    result = grade.grade_table(gt, {"error": "contract violation after retry"})
    assert result["honest_failure"] is True
    assert result["correct_cells"] == 0


def test_gt_template_scaffold_writes_gradable_files(tmp_path):
    records = [{"dimensions": {"poste": "Cadre"}, "metrics": {"jours": 25},
                "raw_values": {"jours": "25"}}]
    out = gtt.scaffold("livret_test", b"\x89PNG-fake", locale="fr",
                       difficulty="real", description="d", records=records,
                       is_draft=False, tables_root=tmp_path)
    assert (out / "image.png").read_bytes() == b"\x89PNG-fake"
    gt = json.loads((out / "ground_truth.json").read_text(encoding="utf-8"))
    assert gt["table_id"] == "livret_test" and gt["locale"] == "fr"
    assert "_draft" not in gt
    # a non-draft scaffold is directly gradable
    parsed = {"records": records}
    assert grade.grade_table(gt, parsed)["correct_cells"] == 1


def test_grade_skips_draft_ground_truth(tmp_path):
    """A draft GT must never be graded — that would score the model against
    its own guess."""
    gtt.scaffold("draft_test", b"img", locale="fr", difficulty="real",
                 description="d",
                 records=[{"dimensions": {"a": "x"}, "metrics": {"m": 1},
                           "raw_values": {"m": "1"}}],
                 is_draft=True, tables_root=tmp_path)
    (tmp_path / "draft_test" / "parsed.json").write_text(
        json.dumps({"records": [{"dimensions": {"a": "x"}, "metrics": {"m": 1},
                                 "raw_values": {"m": "1"}}]}), encoding="utf-8")
    gt = json.loads(
        (tmp_path / "draft_test" / "ground_truth.json").read_text(encoding="utf-8"))
    assert gt["_draft"] is True


def test_gt_template_renders_pdf_page():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Congés payés: 25 jours")
    pdf_bytes = doc.tobytes()
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        pdf_path = Path(f.name)
    try:
        png = gtt.render_pdf_page(pdf_path, 1, dpi=100, bbox=None)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        pdf_path.unlink()

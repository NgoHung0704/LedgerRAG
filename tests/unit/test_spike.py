"""Sanity checks for the Phase 0 spike harness itself (generator + grader)."""

import sys
from pathlib import Path

SPIKE_DIR = str(Path(__file__).resolve().parents[2] / "spike")
if SPIKE_DIR not in sys.path:
    sys.path.insert(0, SPIKE_DIR)

import grade  # noqa: E402
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

"""Phase 3 confidence signals: structural, double-read agreement, arithmetic."""

from tablerag.ingestion.confidence import (
    arithmetic_check,
    assess,
    double_read_agreement,
    structural_consistency,
)


def rec(dims: dict, metrics: dict) -> dict:
    return {"dimensions": dims, "metrics": metrics,
            "raw_values": {k: str(v) for k, v in metrics.items()}}


# ---------------------------------------------------------------- structural

GOOD_HTML = ("<table><tr><th>Pays</th><th>CA</th><th>Vol</th></tr>"
             "<tr><td>Maroc</td><td>100</td><td>5</td></tr>"
             "<tr><td>France</td><td>200</td><td>7</td></tr></table>")


def test_structural_ok():
    records = [rec({"pays": "Maroc"}, {"ca": 100, "vol": 5}),
               rec({"pays": "France"}, {"ca": 200, "vol": 7})]
    score, detail = structural_consistency(GOOD_HTML, records)
    assert score == 1.0
    assert detail["data_rows"] == 2


def test_structural_flags_more_metric_cells_than_slots():
    records = [rec({"p": f"x{i}"}, {"a": i, "b": i, "c": i, "d": i})
               for i in range(10)]  # 40 metric cells vs 6 td slots
    score, _ = structural_consistency(GOOD_HTML, records)
    assert score < 1.0


def test_structural_counts_spans():
    html = ('<table><tr><td rowspan="2">A</td><td>1</td></tr>'
            "<tr><td>2</td></tr></table>")
    records = [rec({"g": "A", "r": "1"}, {"v": 1}),
               rec({"g": "A", "r": "2"}, {"v": 2})]
    score, detail = structural_consistency(html, records)
    assert detail["td_slots"] == 4  # rowspan=2 counts twice
    assert score == 1.0


def test_structural_none_without_input():
    assert structural_consistency("", []) is None


# ---------------------------------------------------------------- agreement

def test_agreement_identical_reads():
    a = [rec({"pays": "Maroc", "mois": "janv."}, {"ca": 7462639, "vol": 426})]
    score, detail = double_read_agreement(a, [dict(r) for r in a])
    assert score == 1.0
    assert detail["agreed"] == 2


def test_agreement_catches_rowspan_boundary_divergence():
    """The H/I-type misread: two reads disagree on which rows a merged group
    covers -> different values at the same coordinates -> low agreement."""
    first = [rec({"groupe": "H", "classe": "15"}, {"cotation": 49}),
             rec({"groupe": "H", "classe": "16"}, {"cotation": 52}),
             rec({"groupe": "I", "classe": "17"}, {"cotation": 55})]
    second = [rec({"groupe": "H", "classe": "15"}, {"cotation": 49}),
              rec({"groupe": "I", "classe": "16"}, {"cotation": 52}),  # shifted
              rec({"groupe": "I", "classe": "17"}, {"cotation": 55})]
    score, _ = double_read_agreement(first, second)
    assert score < 0.98  # below the review threshold


def test_agreement_tolerates_renamed_keys():
    a = [rec({"pays": "Maroc"}, {"ca": 100})]
    b = [rec({"country": "maroc"}, {"revenue": 100})]  # same values, new names
    score, _ = double_read_agreement(a, b)
    assert score == 1.0


def test_agreement_tolerates_accent_and_punctuation_noise():
    """The false-positive cause on clean tables: minor spelling drift between
    reads must not read as disagreement (Phase 3 flag-eval fix)."""
    a = [rec({"annee": "2013", "pays": "Algérie",
              "indic": "Taux d'absentéisme"}, {"v": 7462639})]
    b = [rec({"année": "2013", "pays": "Algerie",
              "indic": "Taux dabsenteisme"}, {"v": 7462639})]
    score, _ = double_read_agreement(a, b)
    assert score == 1.0


def test_agreement_identical_free_text_labels_not_falsely_zero():
    records = [rec({"indicateur": "Taux d'absentéisme"}, {"v2023": 4.2, "v2024": 3.8}),
               rec({"indicateur": "Résultat net (k€)"}, {"v2023": -1250.5, "v2024": 2340.0})]
    score, _ = double_read_agreement(records, [dict(r) for r in records])
    assert score == 1.0


# ---------------------------------------------------------------- arithmetic

def _totals_records(t1_total=1316480.0):
    postes = [("Salaires", [812400, 824100]),
              ("Charges", [365580, 370845]),
              ("Formation", [42300, 15800]),
              ("Intérim", [96200, 104500])]
    records = []
    for poste, (t1, t2) in postes:
        records.append(rec({"poste": poste, "periode": "T1"}, {"montant": t1}))
        records.append(rec({"poste": poste, "periode": "T2"}, {"montant": t2}))
    records.append(rec({"poste": "Total", "periode": "T1"},
                       {"montant": t1_total}))
    records.append(rec({"poste": "Total", "periode": "T2"},
                       {"montant": 1315245.0}))
    return records


def test_arithmetic_passes_on_correct_totals():
    score, detail = arithmetic_check(_totals_records())
    assert score == 1.0
    assert detail["checks"] == 2


def test_arithmetic_catches_wrong_total():
    score, detail = arithmetic_check(_totals_records(t1_total=1300000.0))
    assert score < 1.0
    assert detail["failures"][0]["metric"] == "montant"


def test_arithmetic_none_without_totals():
    records = [rec({"pays": "Maroc"}, {"ca": 100})]
    assert arithmetic_check(records) is None


def test_arithmetic_multilingual_labels():
    records = [rec({"land": "DE"}, {"umsatz": 60}),
               rec({"land": "AT"}, {"umsatz": 40}),
               rec({"land": "Gesamt"}, {"umsatz": 100})]
    score, _ = arithmetic_check(records)
    assert score == 1.0


# ---------------------------------------------------------------- combination

def test_assess_good_table_not_flagged():
    records = [rec({"pays": "Maroc"}, {"ca": 100, "vol": 5}),
               rec({"pays": "France"}, {"ca": 200, "vol": 7})]
    report = assess(GOOD_HTML, records, [dict(r) for r in records])
    assert report.needs_review is False
    assert report.confidence >= 0.98


def test_assess_flags_on_arithmetic_failure_even_with_agreement():
    """A failed sum is the strongest signal: flags immediately (SPEC)."""
    records = _totals_records(t1_total=1300000.0)
    report = assess("", records, [dict(r) for r in records])
    assert report.needs_review is True


def test_assess_flags_on_low_agreement():
    a = [rec({"x": "1"}, {"m": 10}), rec({"x": "2"}, {"m": 20})]
    b = [rec({"x": "1"}, {"m": 10}), rec({"x": "2"}, {"m": 99})]
    report = assess("", a, b)
    assert report.needs_review is True
    assert report.detail["signals"]["agreement"] < 0.98


def test_assess_no_signals_is_honest_zero():
    report = assess("", [], None)
    assert report.confidence == 0.0
    assert report.needs_review is True

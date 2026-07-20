"""Regression tests for the eval-qa grader, built from REAL answers observed
in run 2 on the deployment box (2026-07-20).

Run 2 exposed two grading defects that made the gate lie in both directions:
  - three correct refusals scored as trap failures (surface-form phrase list:
    "ne contienNENT", "aucune RÉFÉRENCE", and a refusal written in Chinese);
  - two wrong answers scored as passes, because the model pasted a table that
    contained the expected string while its prose asserted something else.
Both are pinned here so the gate cannot silently regress to over-reporting.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval" / "qa"))

from run_eval_qa import grade, is_refusal, _norm, prose_only  # noqa: E402

CITED = [{"filename": "Cotation emplois CETIAT 2023_07_27.pdf"}]
AVENANT = [{"filename": "Avenant du 11 juillet 2023.pdf"}]
GLOSSAIRE = [{"filename": "Glossaire-Classification.pdf"}]


# --- refusals that run 2 wrongly marked as invented answers ----------------

@pytest.mark.parametrize("answer", [
    # p2 — "ne contienNENT" is not a superstring of the old "ne contient"
    "L'information sur le salaire d'un Directeur(trice) au CETIAT en 2019 n'est "
    "pas présente dans les documents fournis. Les sources fournissent des "
    "informations concernant la classification et l'évolution des salaires, "
    "mais ne contiennent pas de données historiques précises.",
    # p5 — "aucune référence" was not in the old literal list
    "Les informations fournies ne contiennent aucune référence au groupe "
    "d'emplois K. Les groupes et classes d'emploi mentionnés s'arrêtent au "
    "groupe F, sans inclure de groupe K. [3][4][5]",
    # p7 — the chat model drifted to Chinese and refused there
    "根据提供的信息，2026年的最低工资等级具体数值没有直接给出。"
    "因此，根据现有资料，无法准确回答2026年最低工资的具体数值是多少。",
])
def test_honest_refusals_are_recognized(answer):
    assert is_refusal(_norm(prose_only(answer)))
    ok, detail = grade({"type": "trap", "expected_answer_contains": []},
                       answer, AVENANT, None)
    assert ok, detail


# --- wrong answers that run 2 wrongly passed on a pasted table ------------

def test_wrong_prose_claim_does_not_pass_on_pasted_table():
    """c5: prose says Comptable -> classe 2 (wrong); the expected '22 à 24'
    only appears inside a dumped grid."""
    answer = (
        "Selon le tableau présent dans les sources [6], la cotation du poste de "
        "Comptable correspond à la classe d'emploi 2.\n\n"
        "| Cotations | Classes d’emplois |\n"
        "|-----------|------------------|\n"
        "| 19 à 21   | 5                |\n"
        "| 22 à 24   | 6                |\n\n"
        "Donc, la cotation du poste de Comptable est 2 [6][7].")
    ok, detail = grade(
        {"type": "table", "expected_answer_contains": ["22 à 24"],
         "expected_doc": "Cotation emplois CETIAT 2023_07_27.pdf"},
        answer, CITED, None)
    assert not ok and "missing" in detail


def test_explicit_non_answer_does_not_pass_on_pasted_table():
    """c8: the model says it cannot determine the cotation, then pastes a grid
    containing '40 à 42'."""
    answer = (
        "根据提供的文档，无法直接确定“Ingénieur(e) Commercial(e)”的具体职位等级。\n\n"
        "| Cotations | Classes d’emplois |\n"
        "| 40 à 42   | 12                |\n\n"
        "综上所述，无法确定 Ingénieur(e) Commercial(e) 的具体 cotation。")
    ok, detail = grade(
        {"type": "table", "expected_answer_contains": ["40 à 42"],
         "expected_doc": "Cotation emplois CETIAT 2023_07_27.pdf"},
        answer, CITED, None)
    assert not ok


# --- answers that were genuinely right must keep passing -----------------

@pytest.mark.parametrize("answer,expected,cites", [
    # c3 — states the classes in prose, and also pastes the table
    ("Les classes d'emploi qui appartiennent au groupe d'emplois I sont les "
     "classes 17 et 18.\n\n| 55 à 57 | 17 | I |\n| 58 à 60 | 18 | I |\n",
     ["17", "18"], CITED),
    # a6 — value stated in prose, table pasted alongside
    ("Pour la classe d'emploi 12 dans le groupe F, entre 2 et 4 ans "
     "d'expérience, le montant est de « 31 185 ».\n\n| F | 12 | 29 700 |",
     ["31 185"], AVENANT),
    # a5 — NBSP-grouped number in bold prose
    ("Selon le barème adapté du groupe F pour les salariés débutants avec "
     "moins de 2 ans d'expérience, le montant pour la classe 11 est de "
     "**28 200** [1][2].", ["28 200"], AVENANT),
    # g7 — bullet list (not a markdown table, must survive prose_only)
    ("Les activités du domaine Maintenance incluent :\n\n- Diagnostic\n"
     "- Démontage\n- Dépannage\n- Traçabilité\n", ["Diagnostic", "Dépannage"],
     GLOSSAIRE),
    # a13 — long legal prose with a quoted citation
    ("L'obligation d'application du barème unique national est reportée au "
     "plus tard au 1er janvier 2030.", ["2030"], AVENANT),
    # a11 — "n'excédant pas" must not read as a refusal
    ("Le taux de la cotisation garantie de branche pour les cadres est de "
     "1,12 % de la rémunération brute, pour la part n'excédant pas la "
     "tranche 2 [1].", ["1,12"], AVENANT),
])
def test_correct_answers_still_pass(answer, expected, cites):
    ok, detail = grade(
        {"type": "table", "expected_answer_contains": expected,
         "expected_doc": cites[0]["filename"]}, answer, cites, None)
    assert ok, detail


def test_hedged_answer_fails_even_with_expected_string_in_prose():
    """An answer may not both refuse and score: honesty is graded, not luck."""
    ok, detail = grade(
        {"type": "table", "expected_answer_contains": ["52 à 54"],
         "expected_doc": "Cotation emplois CETIAT 2023_07_27.pdf"},
        "Les documents ne contiennent pas cette information, mais il "
        "s'agirait peut-être de 52 à 54.", CITED, None)
    assert not ok and "refuses" in detail

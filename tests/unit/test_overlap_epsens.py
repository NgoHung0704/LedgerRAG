"""Overlap detection against the real sibling tables in the EPSENS corpus.

Six fund factsheets, all "Reporting au 30/09/2021", all from the same manager,
all built from the same template. Their tables share a structure exactly and
differ only in the numbers and in WHICH FUND they describe — which is the case
the overlap feature exists for, and the case a reader cannot spot in an answer
that quietly merges two of them.

The headers below are transcribed from the documents, not invented. Three
distinct table families repeat across the funds:

  Performances cumulées (en %)   | 1 mois | 2021 | 1 an | 3 ans | 5 ans | 10 ans
  Performances annualisées (en %)|                 1 an | 3 ans | 5 ans | 10 ans
  Performances annuelles (en %)  | 2020 | 2019 | 2018 | 2017 | 2016

The prose is a sibling too: the "Economie et Marchés" column is byte-identical
in all six documents, which is the text-side version of the same hazard.
"""

import uuid

from tablerag.query.overlap import (
    group_overlapping,
    header_signature,
    jaccard,
    subject_signature,
)
from tablerag.query.pipeline import SourceBlock

CUMULEES = (
    "<table><tr><th>Performances cumulées (en %)</th><th>1 mois</th>"
    "<th>2021</th><th>1 an</th><th>3 ans</th><th>5 ans</th><th>10 ans</th></tr>"
    "<tr><td>Portefeuille</td><td>{a}</td><td>{b}</td><td>{c}</td>"
    "<td>{d}</td><td>{e}</td><td>{f}</td></tr></table>")
ANNUELLES = (
    "<table><tr><th>Performances annuelles (en %)</th><th>2020</th>"
    "<th>2019</th><th>2018</th><th>2017</th><th>2016</th></tr>"
    "<tr><td>Portefeuille</td><td>14,82</td><td>16,65</td><td>-12,25</td>"
    "<td>9,92</td><td>3,26</td></tr></table>")
ANNUALISEES = (
    "<table><tr><th>Performances annualisées (en %)</th><th>1 an</th>"
    "<th>3 ans</th><th>5 ans</th><th>10 ans</th></tr>"
    "<tr><td>Portefeuille</td><td>20,17</td><td>9,43</td><td>8,51</td>"
    "<td>9,55</td></tr></table>")

# the real figures, so a reader of this test can check them against the PDFs
DEFIS = CUMULEES.format(a="-2,58", b="9,42", c="20,17", d="31,04",
                        e="50,46", f="148,90")
FLEXI = CUMULEES.format(a="-0,08", b="-0,46", c="-0,33", d="0,08",
                        e="-0,61", f="7,42")
VERTES = CUMULEES.format(a="-0,83", b="-1,91", c="-1,01", d="4,96",
                         e="2,43", f="18,60")
MONETAIRE = CUMULEES.format(a="-0,06", b="-0,52", c="-0,66", d="-1,50",
                            e="-2,19", f="-1,20")

# identical in all six documents, verbatim
ECONOMIE = (
    "En France, les prix ont augmenté de 2.1% en septembre par rapport au même "
    "mois de l'année précédente. L'inflation se retrouve à un point haut, elle "
    "n'avait pas atteint ce niveau depuis 2018.")


def _table(html: str, filename: str) -> SourceBlock:
    return SourceBlock(
        kind="table", doc_id=uuid.uuid4(), filename=filename, page=1,
        element_id=uuid.uuid4(), content=html, snippet="", score=0.5,
        crop_image_path="c.png")


def test_the_same_performance_table_from_four_funds_shares_one_signature():
    signatures = {header_signature(html)
                  for html in (DEFIS, FLEXI, VERTES, MONETAIRE)}
    assert len(signatures) == 1
    assert None not in signatures


def test_the_three_table_families_in_one_factsheet_stay_apart():
    # a document holds all three; grouping them together would tell the model
    # that a 10-year cumulative return and a 2018 annual return are the same
    # kind of thing, which is how a wrong number gets quoted confidently
    assert len({header_signature(DEFIS),
                header_signature(ANNUELLES),
                header_signature(ANNUALISEES)}) == 3


def test_four_funds_performance_tables_are_grouped_as_look_alikes():
    blocks = [_table(DEFIS, "EPSENS DEFIS - 100005.pdf"),
              _table(ANNUELLES, "EPSENS DEFIS - 100005.pdf"),
              _table(FLEXI, "EPSENS FLEXI TAUX COURT ISR SOLIDAIRE - 100312.pdf"),
              _table(VERTES, "EPSENS OBLIGATIONS VERTES ISR - 6006.pdf"),
              _table(MONETAIRE, "EPSENS MONETAIRE ISR - 4004.pdf")]
    assert group_overlapping(blocks) == [[0, 2, 3, 4]]


def _text(content: str, filename: str) -> SourceBlock:
    return SourceBlock(
        kind="text", doc_id=uuid.uuid4(), filename=filename, page=2,
        element_id=uuid.uuid4(), chunk_id=uuid.uuid4(), content=content,
        snippet="", score=0.5, crop_image_path="c.png")


def test_the_market_commentary_repeated_in_two_funds_is_grouped():
    # this paragraph is byte-identical in all six factsheets. Retrieval will
    # surface several copies, and an answer must not present one fund's page as
    # if the commentary were specific to that fund.
    blocks = [_text(ECONOMIE, "EPSENS DEFIS - 100005.pdf"),
              _text(ECONOMIE, "EPSENS MONETAIRE ISR - 4004.pdf")]
    assert group_overlapping(blocks) == [[0, 1]]


def test_two_different_fund_strategies_are_left_alone():
    rhone = ("Ce fonds solidaire qui favorise une épargne de proximité s'adresse "
             "à des investisseurs en quête du renouveau économique de leur "
             "région. Il participe au dynamisme économique régional en finançant "
             "les entreprises locales.")
    flexi = ("Ce fonds est géré activement et vise à surperformer son indice de "
             "référence obligataire court et monétaire diminué des frais. Il est "
             "investi jusqu'à 100% sur les marchés monétaires et obligataires.")
    blocks = [_text(rhone, "EPSENS RHONE ALPES AUVERGNE SOLIDAIRE - 1008.pdf"),
              _text(flexi, "EPSENS FLEXI TAUX COURT ISR SOLIDAIRE - 100312.pdf")]
    assert group_overlapping(blocks) == []


def test_the_prose_in_this_corpus_duplicates_exactly_rather_than_loosely():
    """What the text side of this corpus actually looks like, measured.

    The synthetic fixture in test_overlap.py models a near-duplicate: two
    passages sharing a heavy administrative preamble, where stopword removal is
    what pulls them apart. This corpus does NOT work that way. Its repeated
    prose is repeated VERBATIM — the market commentary, the ESG definition, the
    Legrand analysis — while genuinely different paragraphs share almost
    nothing even before filtering (measured: 0.067 unfiltered, 0.028 filtered).

    Recorded as a test so nobody tunes the threshold against an imagined middle
    case that this corpus does not contain."""
    strategie_a = ("Ce fonds solidaire qui favorise une épargne de proximité "
                   "s'adresse à des investisseurs en quête du renouveau "
                   "économique de leur région.")
    strategie_b = ("Ce fonds est géré activement et vise à surperformer son "
                   "indice de référence obligataire court et monétaire diminué "
                   "des frais.")
    assert jaccard(subject_signature(ECONOMIE), subject_signature(ECONOMIE)) == 1.0
    assert jaccard(subject_signature(strategie_a),
                   subject_signature(strategie_b)) < 0.1

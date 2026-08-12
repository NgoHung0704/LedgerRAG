"""A row filed under nothing cannot be told from seventeen like it.

The EPSENS corpus holds six funds in three reporting editions, every table built
from one template. `text_repr` says "5 ans: 50,46" and nothing about whose or
when, so retrieval cannot prefer the right row and the assistant falls back to
reading the flattened grid - which is where the wrong-column answers come from.
"""

from tablerag.indexing import record_index_text

ROW = "5 ans: 50,46 | 3 ans: 31,04"


def test_the_row_is_filed_under_its_document_and_heading():
    text = record_index_text(ROW, "EPSENS DEFIS - 100005.pdf",
                             "PERFORMANCES DU FONDS")
    assert "EPSENS DEFIS - 100005.pdf" in text
    assert "PERFORMANCES DU FONDS" in text
    assert ROW in text


def test_two_funds_same_row_no_longer_produce_the_same_text():
    defis = record_index_text(ROW, "EPSENS DEFIS - 100005.pdf", "PERFORMANCES")
    flexi = record_index_text(ROW, "EPSENS FLEXI TAUX COURT - 100312.pdf",
                              "PERFORMANCES")
    assert defis != flexi, "identical rows from different funds must differ"


def test_a_row_with_no_scope_is_left_exactly_as_it_was():
    # rows indexed before this existed, and any caller that has no document to
    # name, must produce byte-identical text - or every one of them re-embeds
    assert record_index_text(ROW) == ROW
    assert record_index_text(ROW, "", "") == ROW


def test_the_row_itself_is_never_lost_to_the_scope():
    text = record_index_text(ROW, "a-very-long-document-name.pdf", "A HEADING")
    assert text.endswith(ROW)

"""Local sparse lexical vectors (Phase 4 hybrid retrieval)."""

from tablerag.core.sparse import sparse_vector, tokenize


def test_tokenize_multilingual_accents_folded():
    assert tokenize("Chargé d'essais/étalonnages") == \
        ["charge", "essais", "etalonnages", "essais/etalonnages"]


def test_tokenize_keeps_rare_code_tokens():
    tokens = tokenize("Référence AX-1042, période T1 2013")
    assert "ax" in tokens and "1042" in tokens
    assert "ax-1042" in tokens          # compound kept whole for exact match
    assert "t1" in tokens and "2013" in tokens


def test_tokenize_drops_single_letters_keeps_digits():
    assert tokenize("a 1 to T1") == ["1", "to", "t1"]


def test_sparse_vector_counts_term_frequency():
    indices, values = sparse_vector("total total détail")
    assert len(indices) == 2
    assert sorted(values) == [1.0, 2.0]
    assert indices == sorted(indices)   # qdrant wants sorted u32 indices
    assert all(0 <= i < 2**32 for i in indices)


def test_sparse_vector_stable_across_calls():
    assert sparse_vector("7 462 639 EUR") == sparse_vector("7 462 639 EUR")


def test_query_and_document_share_token_space():
    """The whole point of hybrid: a rare query token must hit the doc token."""
    doc_idx, _ = sparse_vector("Barème AX-1042 pour la classe 16")
    query_idx, _ = sparse_vector("ax-1042")
    assert set(query_idx) & set(doc_idx)


def test_empty_text():
    assert sparse_vector("") == ([], [])
    assert sparse_vector("???!!!") == ([], [])

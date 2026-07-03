from tablerag.ingestion.chunking import chunk_text, estimate_tokens


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_single_chunk():
    chunks = chunk_text("Bonjour le monde.")
    assert len(chunks) == 1
    assert chunks[0].text == "Bonjour le monde."
    assert chunks[0].token_count == estimate_tokens(chunks[0].text)


def test_chunks_respect_target_size():
    paragraphs = "\n\n".join(f"Paragraphe {i}. " + "mot " * 60 for i in range(30))
    chunks = chunk_text(paragraphs, target_tokens=100, overlap_ratio=0.1)
    assert len(chunks) > 1
    # a chunk may exceed target only by its final unit, never wildly
    for chunk in chunks:
        assert chunk.token_count <= 200


def test_overlap_carries_trailing_content():
    paragraphs = "\n\n".join(f"P{i} " + "x" * 100 for i in range(20))
    chunks = chunk_text(paragraphs, target_tokens=100, overlap_ratio=0.5)
    assert len(chunks) > 2
    overlapping = sum(
        1 for a, b in zip(chunks, chunks[1:])
        if any(part in b.text for part in a.text.split("\n\n"))
    )
    assert overlapping > 0, "expected some paragraph overlap between chunks"


def test_oversized_paragraph_is_split():
    huge = "word " * 3000  # far beyond target, no sentence breaks
    chunks = chunk_text(huge, target_tokens=100)
    assert len(chunks) > 1


def test_no_overlap_when_ratio_zero():
    paragraphs = "\n\n".join(f"Para {i} " + "y" * 200 for i in range(10))
    chunks = chunk_text(paragraphs, target_tokens=100, overlap_ratio=0.0)
    seen: set[str] = set()
    for chunk in chunks:
        for para in chunk.text.split("\n\n"):
            assert para not in seen, "paragraph duplicated despite zero overlap"
            seen.add(para)

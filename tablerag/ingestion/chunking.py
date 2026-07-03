"""Paragraph-based chunking: ~target tokens per chunk, ~10% overlap.

Token counts are estimated (chars/4) — good enough for sizing chunks and
cheap enough to run on every paragraph. Deterministic and dependency-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class TextChunk:
    text: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _split_units(text: str, target_tokens: int) -> list[str]:
    """Paragraphs; oversized paragraphs fall back to sentences, then to
    fixed-size character windows."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if estimate_tokens(para) <= target_tokens:
            units.append(para)
            continue
        for sent in _SENTENCE_RE.split(para):
            sent = sent.strip()
            if not sent:
                continue
            if estimate_tokens(sent) <= target_tokens:
                units.append(sent)
            else:
                window = target_tokens * 4
                units.extend(sent[i:i + window].strip()
                             for i in range(0, len(sent), window))
    return units


def chunk_text(text: str, target_tokens: int = 500,
               overlap_ratio: float = 0.10) -> list[TextChunk]:
    units = _split_units(text, target_tokens)
    if not units:
        return []

    overlap_budget = int(target_tokens * overlap_ratio)
    chunks: list[TextChunk] = []
    buffer: list[str] = []
    buffer_tokens = 0

    def emit() -> None:
        if buffer:
            joined = "\n\n".join(buffer)
            chunks.append(TextChunk(text=joined, token_count=estimate_tokens(joined)))

    for unit in units:
        unit_tokens = estimate_tokens(unit)
        if buffer and buffer_tokens + unit_tokens > target_tokens:
            emit()
            # carry trailing units as overlap into the next chunk
            tail: list[str] = []
            tail_tokens = 0
            for prev in reversed(buffer):
                prev_tokens = estimate_tokens(prev)
                if tail_tokens + prev_tokens > overlap_budget:
                    break
                tail.insert(0, prev)
                tail_tokens += prev_tokens
            buffer = tail
            buffer_tokens = tail_tokens
        buffer.append(unit)
        buffer_tokens += unit_tokens
    emit()
    return chunks

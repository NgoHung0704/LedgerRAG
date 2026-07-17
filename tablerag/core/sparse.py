"""Local sparse lexical vectors for hybrid retrieval (SPEC Phase 4).

Why local: Ollama only returns dense embeddings (bge-m3's sparse head isn't
exposed), and standing up another inference server just for lexical matching
would violate the "one-command self-host" story. Instead: term-frequency
sparse vectors computed here (pure Python, CPU), with **IDF applied
server-side by Qdrant** (`Modifier.IDF`) — BM25-style scoring without any new
dependency, fully local (C1).

This is the signal that catches rare tokens dense embeddings blur: product
codes ("AX-1042"), period tokens ("T1 2013"), proper names — the exact
motivation in the spec. Query and documents MUST use this same tokenizer.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter

# alnum runs; compounds like "ax-1042" / "t1/2013" also emitted whole
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_COMPOUND_RE = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)+")


def _normalize(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    """Lowercased, accent-stripped tokens. Hyphen/slash compounds are emitted
    both whole ("ax-1042") and split ("ax", "1042") so exact-code queries and
    partial mentions both match."""
    normalized = _normalize(text or "")
    tokens = _TOKEN_RE.findall(normalized)
    tokens += _COMPOUND_RE.findall(normalized)
    return [t for t in tokens if len(t) > 1 or t.isdigit()]


def _token_index(token: str) -> int:
    """Stable 32-bit index for a token (Qdrant sparse indices are u32)."""
    return int.from_bytes(
        hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest(), "big")


def sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """(indices, values) with values = term frequency; IDF is applied by
    Qdrant at query time. Empty text -> empty vector."""
    counts = Counter(_token_index(t) for t in tokenize(text))
    if not counts:
        return [], []
    indices = sorted(counts)
    return indices, [float(counts[i]) for i in indices]

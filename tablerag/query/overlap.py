"""Which retrieved sources are covering the SAME subject as each other.

A corpus of insurance notices and HR grids is full of tables that share a
structure and differ only in their numbers: the 2024 guarantee table and the
2025 one, the technical department's scale and the administrative one. Both are
retrieved, both look right, and an answer that merges them is wrong in a way
nobody can see.

What is computed here is deliberately shallow: WHICH sources belong together,
never WHAT they say differently. The second question needs the meaning of the
text, which is the model's job — a machine-made claim about it would be a
fabrication sitting inside the context window, which is the worst place for one.

Two signatures, because the two kinds of source fail differently:

  - tables: their header row. Siblings share it exactly; unrelated tables do
    not. No threshold, no tuning.
  - text: the RARE words. Jaccard over every word groups any two paragraphs of
    French administrative prose, because they all repeat the same hundred
    words; dropping those leaves what the passage is actually about.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# the words a French (and English) document repeats on every page: they say
# nothing about which subject a passage covers. Like the threshold below, this
# list is a starting point measured on two documents, not a finished one — a
# word that turns out to be boilerplate in the corpus belongs here.
_STOPWORDS = frozenset("""
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma
mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se
ses son sur ta te tes toi ton tu un une vos votre vous est sont etre a ils
plus tout tous toute toutes autre autres cas selon dont ainsi entre sans
present presenta cette cet leurs doit doivent peut peuvent aussi donc chaque remis
concerne concernant demande disposition fait legales legale vigueur tenu tenue
applicable applicables titre article alinea paragraphe suivant suivante
document salarie salaries entreprise conformement dispositions
the of and to in for is are be as by or an at this that with from it its on
""".split())

_TAG = re.compile(r"<[^>]+>")
_HEADER_CELL = re.compile(r"<th\b[^>]*>(.*?)</th>", re.I | re.S)
_WORD = re.compile(r"[a-zA-ZÀ-ÖØ-öø-ÿ]{3,}")


def _fold(text: str) -> str:
    """Lowercase, strip accents and anything that is not a letter."""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"[^a-z]+", "", stripped.lower())


def header_signature(html: str) -> str | None:
    """A hash of the table's header cells, or None when it has no header.

    Digits are folded out with everything else, so the 2024 table and the 2025
    table hash the same — which is the entire point: they ARE the same table,
    filled in at two moments."""
    cells = [_fold(_TAG.sub(" ", cell)) for cell in _HEADER_CELL.findall(html)]
    cells = [c for c in cells if c]
    if not cells:
        return None
    joined = "|".join(sorted(cells))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def subject_signature(text: str) -> frozenset[str]:
    """The rare content words of a passage — what it is ABOUT."""
    words = {_fold(w) for w in _WORD.findall(text)}
    return frozenset(w for w in words if w and w not in _STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def group_overlapping(blocks, threshold: float = 0.5) -> list[list[int]]:
    """Indices of blocks covering the same subject, as groups of 2 or more.

    `threshold` is a starting value, NOT a measured one. It must be set from
    the corpus before this is trusted — see the plan's measurement task.
    Grouping is greedy and pairwise, not transitive: a block joins the first
    group it matches and is then spoken for. Chains where A matches B and B
    matches C but A does not match C therefore yield only the first pair. That
    is deliberate — a transitive closure over a fuzzy similarity drifts, and one
    wrong link merges two unrelated subjects."""
    groups: list[list[int]] = []
    used: set[int] = set()
    signatures = [header_signature(b.content) if b.kind == "table"
                  else subject_signature(b.content) for b in blocks]
    for i, sig_i in enumerate(signatures):
        if i in used or not sig_i:
            continue
        group = [i]
        for j in range(i + 1, len(blocks)):
            sig_j = signatures[j]
            if j in used or not sig_j or blocks[i].kind != blocks[j].kind:
                continue
            same = (sig_i == sig_j if blocks[i].kind == "table"
                    else jaccard(sig_i, sig_j) >= threshold)
            if same:
                group.append(j)
        if len(group) > 1:
            groups.append(group)
            used.update(group)
    return groups

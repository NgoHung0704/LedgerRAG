"""What a retrieved chunk needs around it in order to mean anything.

Retrieval matches a chunk because it holds the keyword. But a paragraph that
leads INTO the answer, and the one that continues it, hold no keyword at all —
they are the sentences either side, and they are why the matched one is
readable. The same is true of the table or the chart the prose is describing:
they are on the page, they are the point, and no word in them was searched for.

Two rules, and the second is a fence rather than a feature:

  - a text winner takes the element immediately before and after it in reading
    order, within its own document.
  - any winner takes the tables and figures on its own page.

Tables and figures take NOTHING. Without that, a table pulls its page, whose
text pulls its own neighbours, whose pages pull more tables, and one match
drags in a chapter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class NeighbourCandidate:
    element_id: uuid.UUID
    doc_id: uuid.UUID
    page: int
    y: float
    x: float
    type: str  # 'text' | 'table' | 'figure'


def choose_neighbours(candidates: list[NeighbourCandidate],
                      winners: list[uuid.UUID]) -> list[uuid.UUID]:
    """Element ids to pull in beside the winners, in reading order, no repeats."""
    won = set(winners)
    ordered = sorted(candidates, key=lambda c: (c.doc_id.int, c.page, c.y, c.x))
    by_id = {c.element_id: c for c in ordered}
    picked: list[uuid.UUID] = []

    def take(element_id: uuid.UUID) -> None:
        if element_id not in won and element_id not in picked:
            picked.append(element_id)

    for index, candidate in enumerate(ordered):
        if candidate.element_id not in won:
            continue
        if candidate.type == "text":
            for step in (-1, 1):
                near = index + step
                if 0 <= near < len(ordered) \
                        and ordered[near].doc_id == candidate.doc_id:
                    take(ordered[near].element_id)
        for other in ordered:
            if (other.doc_id == candidate.doc_id
                    and other.page == candidate.page
                    and other.type in ("table", "figure")):
                take(other.element_id)
    return [element_id for element_id in picked if element_id in by_id]

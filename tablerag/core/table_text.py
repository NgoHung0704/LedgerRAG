"""Table HTML -> text renderings, shared by both pipelines.

Lives in `core/` on purpose: ingestion needs these to build indexable text,
and query needs them to build model context, but the two pipelines must never
import each other (principle #1) — they meet here and in storage only.

Nothing in this module talks to a model, a database or the network: it is pure
string work, so both sides can rely on it being deterministic and cheap.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")


class TableParser(HTMLParser):
    """Rows of cell dicts: {tag, colspan, rowspan, text} with <br> kept as \\n."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            def _span(v):
                try:
                    return max(1, int(v))
                except (TypeError, ValueError):
                    return 1
            self._cell = {"tag": tag, "colspan": _span(a.get("colspan")),
                          "rowspan": _span(a.get("rowspan")), "text": ""}
        elif tag == "br" and self._cell is not None:
            self._cell["text"] += "\n"  # keep in-cell line breaks

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._cell is not None:
            self._cell["text"] += "\n"

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data


def build_occupancy(rows: list[list[dict]]) -> dict[tuple[int, int], dict]:
    """Map every (row, col) the table covers to the cell occupying it, so
    merged cells are resolvable by position instead of by sequence."""
    occ: dict[tuple[int, int], dict] = {}
    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while (r, c) in occ:
                c += 1
            cell["r"], cell["c"] = r, c
            for dr in range(cell["rowspan"]):
                for dc in range(cell["colspan"]):
                    occ[(r + dr, c + dc)] = cell
            c += cell["colspan"]
    return occ


def html_to_text(html: str | None) -> str:
    """Plain text of a table's HTML, cells space-separated.

    Indexable text for the table_summaries collection when no LLM summary
    exists (failed/flagged parses): a parsed table must always be retrievable,
    otherwise the honest-failure path (LOW CONFIDENCE source + original image)
    can never trigger for it.
    """
    if not html:
        return ""
    from html import unescape

    return WS.sub(" ", unescape(_TAG.sub(" ", html))).strip()


def flatten_table_for_context(html: str | None) -> str:
    """Render a table as markdown with every merged cell EXPANDED.

    Display HTML uses rowspan/colspan to mirror the printed table, but reading
    it back requires tracking which columns an earlier row still occupies —
    something small chat models get wrong in a very specific, damaging way:

        <tr><td>19 à 21</td><td>5</td><td rowspan="2">C</td><td>Assistant…</td></tr>
        <tr><td>22 à 24</td><td>6</td><td>Comptable</td></tr>

    The second row has three cells because column 3 is still covered by "C",
    so "Comptable" belongs to column 4 (Emplois). Models instead read it
    positionally as column 3 (Groupes) and answer "Comptable is in group B";
    likewise a group spanning two rows gets reported as covering only the
    first one.

    So the context representation repeats spanned values on every row they
    cover: each line is then self-contained and needs no cross-row reasoning.
    Falls back to plain text (never raises) — context must always be produced.
    """
    if not html:
        return ""
    try:
        parser = TableParser()
        parser.feed(html)
        if not parser.rows:
            return html_to_text(html)
        occ = build_occupancy(parser.rows)
        if not occ:
            return html_to_text(html)
        n_rows = max(r for r, _ in occ) + 1
        n_cols = max(c for _, c in occ) + 1

        def cell_text(r: int, c: int) -> str:
            raw = (occ.get((r, c)) or {}).get("text", "")
            # in-cell line breaks would break the markdown row
            parts = [WS.sub(" ", line).strip() for line in raw.split("\n")]
            return " / ".join(p for p in parts if p)

        grid = [[cell_text(r, c) for c in range(n_cols)] for r in range(n_rows)]
        lines = ["| " + " | ".join(grid[0]) + " |",
                 "|" + "|".join(["---"] * n_cols) + "|"]
        lines += ["| " + " | ".join(row) + " |" for row in grid[1:]]
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — degrade to text, never lose the table
        return html_to_text(html)

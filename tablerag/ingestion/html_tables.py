"""Deterministic display cleanup: collapse vertically-repeated data cells into
rowspan so the rendered table matches the merged look of the original.

The grid-hint forward-fills merged row labels so the RECORDS are complete
(the group label on every spanned row); a side effect is that the VLM may emit
that label as repeated <td> cells instead of one merged cell. This pass
re-merges identical vertical runs of DATA cells into rowspan for DISPLAY only —
it never touches the records. Idempotent (already-merged HTML is unchanged) and
fail-safe (any parse problem returns the original HTML).
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


class _TableParser(HTMLParser):
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


def _build_occupancy(rows: list[list[dict]]) -> dict[tuple[int, int], dict]:
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


def collapse_vertical_merges(html: str | None) -> str | None:
    if not html or "<t" not in html.lower():
        return html
    try:
        parser = _TableParser()
        parser.feed(html)
        rows = parser.rows
        if not rows:
            return html
        occ = _build_occupancy(rows)
        n_rows = len(rows)
        n_cols = max((c for _, c in occ), default=-1) + 1

        for col in range(n_cols):
            # the origin cells occupying this column, top to bottom
            column: list[dict] = []
            r = 0
            while r < n_rows:
                cell = occ.get((r, col))
                if cell is None:
                    r += 1
                elif cell["r"] == r and cell["c"] == col:
                    column.append(cell)
                    r += cell["rowspan"]
                else:
                    r += 1
            # merge adjacent identical, non-empty data cells (never headers,
            # never empty cells, single-column only)
            i = 0
            while i < len(column):
                cur = column[i]
                j = i + 1
                while (j < len(column) and cur["tag"] == "td"
                       and column[j]["tag"] == "td"
                       and cur["colspan"] == 1 and column[j]["colspan"] == 1
                       and _norm(cur["text"])
                       and _norm(cur["text"]) == _norm(column[j]["text"])):
                    cur["rowspan"] += column[j]["rowspan"]
                    column[j]["removed"] = True
                    j += 1
                i = j

        out = ["<table>"]
        for row in rows:
            cells = []
            for cell in row:
                if cell.get("removed"):
                    continue
                attrs = ""
                if cell["rowspan"] > 1:
                    attrs += f' rowspan="{cell["rowspan"]}"'
                if cell["colspan"] > 1:
                    attrs += f' colspan="{cell["colspan"]}"'
                cells.append(
                    f'<{cell["tag"]}{attrs}>{escape(_norm(cell["text"]))}'
                    f'</{cell["tag"]}>')
            out.append("  <tr>" + "".join(cells) + "</tr>")
        out.append("</table>")
        return "\n".join(out)
    except Exception:  # noqa: BLE001 — display cleanup must never break ingestion
        return html

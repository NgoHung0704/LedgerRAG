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

from html import escape

# shared with the query pipeline via core (principle #1: the two pipelines
# never import each other — re-exported here so callers keep one import site)
from tablerag.core.table_text import (  # noqa: F401
    WS as _WS,
    TableParser as _TableParser,
    build_occupancy as _build_occupancy,
    flatten_table_for_context,
    html_to_text,
)


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def _display(text: str) -> str:
    """Emission form of a cell: whitespace normalized per line, line breaks
    preserved as <br> (multi-line PDF cells stay multi-line)."""
    lines = [_WS.sub(" ", line).strip() for line in (text or "").split("\n")]
    return "<br>".join(escape(line) for line in lines if line)


def _labelish_columns(rows: list[list[dict]], n_cols: int) -> set[int]:
    """Columns whose non-empty data cells are mostly text (labels), as opposed
    to numeric columns — only label columns take part in horizontal merging."""
    non_empty = [0] * n_cols
    with_alpha = [0] * n_cols
    for row in rows:
        for cell in row:
            if cell["tag"] != "td":
                continue
            text = _norm(cell["text"])
            if not text:
                continue
            c = cell["c"]
            non_empty[c] += 1
            if any(ch.isalpha() for ch in text):
                with_alpha[c] += 1
    return {c for c in range(n_cols)
            if non_empty[c] > 0 and with_alpha[c] / non_empty[c] >= 0.5}


def _merge_horizontal_blanks(rows: list[list[dict]], n_cols: int) -> None:
    """An INTERIOR run of blank cells widens the label cell on its left into
    colspan — reconstructing horizontal merges that the grid extraction turned
    into empty columns (e.g. a Techniques cell spanning family+sub columns).
    Guardrails: both the left column and the blank columns must be label
    columns (numeric columns keep their genuinely-missing blanks), and a run
    that reaches the end of the row is trailing, never merged."""
    labelish = _labelish_columns(rows, n_cols)
    for row in rows:
        cells = [c for c in row if not c.get("removed")]
        for i, cur in enumerate(cells):
            # headers (th) participate too: a blank th between labeled th's is
            # the same colspan-reconstruction case (e.g. a 'Techniques' header
            # spanning family+sub columns). The labelish guard still protects
            # numeric columns, and trailing blanks (empty header over a data
            # column, CETIAT-style) are excluded by the interior-only rule.
            if (cur["tag"] not in ("td", "th") or cur.get("removed")
                    or not _norm(cur["text"]) or cur["c"] not in labelish
                    or cur["rowspan"] != 1):
                continue
            j = i + 1
            run: list[dict] = []
            while (j < len(cells) and cells[j]["tag"] == cur["tag"]
                   and not _norm(cells[j]["text"])
                   and cells[j]["colspan"] == 1 and cells[j]["rowspan"] == 1
                   and cells[j]["c"] in labelish):
                run.append(cells[j])
                j += 1
            # interior only: something non-empty must follow the run
            if run and j < len(cells) and _norm(cells[j]["text"]):
                for blank in run:
                    cur["colspan"] += blank["colspan"]
                    blank["removed"] = True


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
        _merge_horizontal_blanks(rows, n_cols)

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
                    f'<{cell["tag"]}{attrs}>{_display(cell["text"])}'
                    f'</{cell["tag"]}>')
            out.append("  <tr>" + "".join(cells) + "</tr>")
        out.append("</table>")
        return "\n".join(out)
    except Exception:  # noqa: BLE001 — display cleanup must never break ingestion
        return html

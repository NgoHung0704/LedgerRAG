"""Detection gate: are the tables on a real page FOUND at all?

`make eval-tables` grades how well a table is READ, from images already cropped
in spike/tables/. It never asks whether the platform would have found that table
on the page. So a detector can miss the main table of every document in a corpus
and the table gate still reads 88.4 %.

That is not hypothetical. Measured on the box, `EPSENS DEFIS - 100005.pdf` had
ONE table element in the whole document — the risk indicators on page 2 — while
its three performance tables on page 1 were never detected. Every retrieval fix
of that day was therefore powerless on the question "performance cumulée sur
5 ans": the value 50,46 existed nowhere except as page prose.

What is graded here:

  tables    — how many regions the platform accepts on the page, against how
              many a reader sees. Reported, not gated on its own: one detection
              covering two adjacent tables is a different fault from none.
  reachable — whether a specific printed value can be found in ANY accepted
              grid. This is the one that matters, because it is exactly the
              question "could an answer have cited a table for this number".

Drop the PDFs named in detection.jsonl into tests/eval/tables/pdfs/.
No model is called: detection is pure PyMuPDF plus this repo's acceptance rules,
so this runs anywhere the file does.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz

from tablerag.ingestion.layout import detect_tables

# a number printed as 50,46 may be extracted as "50,46" or "50, 46"; compare on
# digits and the separator alone so a spacing artefact is not read as a miss
_TIGHTEN = re.compile(r"\s+")


def _flat(grid) -> str:
    return _TIGHTEN.sub("", " ".join(str(cell or "") for row in grid for cell in row))


def reachable(grids: list, value: str) -> bool:
    """Is this printed value inside any accepted grid?"""
    needle = _TIGHTEN.sub("", value)
    return any(needle in _flat(grid) for grid in grids)


def where(words: list, value: str) -> list[tuple]:
    """Every word box on the page holding this printed value."""
    needle = _TIGHTEN.sub("", value)
    return [tuple(round(v) for v in w[:4]) for w in words
            if needle in _TIGHTEN.sub("", w[4])]


def dump(page, item: dict, found: list) -> None:
    """Say WHY a page failed, since "unreachable" covers four different faults.

    A value can be missing because no region covers it, because a region covers
    it and the grid dropped it, or because it was never in the text layer — a
    chart's outlined text is drawn as curves and belongs to no word at all. The
    fix for each is somewhere else entirely, and the pass/fail line cannot tell
    them apart. Neither could I: two guesses in a row about which one it was."""
    print(f"{'':16} {'':8} {len(found)} accepted region(s):")
    for i, (table, grid) in enumerate(found):
        box = tuple(round(v) for v in table.bbox)
        cols = max((len(row) for row in grid), default=0)
        head = [str(c or "")[:12] for c in (grid[0] if grid else [])][:6]
        print(f"{'':16} {'':8}   #{i} {type(table).__name__:11} {box} "
              f"{len(grid)}x{cols} {head}")

    words = page.get_text("words")
    grids = [g for _, g in found]
    for value in item.get("must_reach", []):
        if reachable(grids, value):
            continue
        spots = where(words, value)
        if not spots:
            print(f"{'':16} {'':8}   {value!r}: in NO word on the page - it is "
                  f"drawn, not written (outlined chart text or an image)")
            continue
        for x0, y0, x1, y1 in spots[:2]:
            covering = [i for i, (t, _) in enumerate(found)
                        if t.bbox[0] <= x0 and t.bbox[1] <= y0
                        and x1 <= t.bbox[2] and y1 <= t.bbox[3]]
            place = (f"inside region #{covering[0]}, dropped by its grid"
                     if covering else "covered by no accepted region")
            print(f"{'':16} {'':8}   {value!r}: at ({x0},{y0}) - {place}")


def proposals(page, found: list) -> str:
    """What became of each region the word detector offered.

    An earlier version of this asked accept_table with NO existing regions, so
    it reported "3 offered, 3 accepted" on a page whose output held two. It was
    blind to the dedupe, which is the one thing worth knowing here: word tables
    are considered last, so a region the ruled or text strategies already put
    down can block a better one. Replayed in the real order, against the real
    regions those strategies produced."""
    from tablerag.ingestion.layout import accept_table, repair_grid
    from tablerag.ingestion.word_tables import WordTable, find_word_tables

    rects = [fitz.Rect(t.bbox) for t, _ in found if not isinstance(t, WordTable)]
    kept = blocked = shape = 0
    for bbox, grid in find_word_tables(page.get_text("words")):
        rect, repaired = fitz.Rect(bbox), repair_grid(grid)
        if accept_table(rect, repaired, "words", rects):
            kept += 1
            rects.append(rect)
        elif accept_table(rect, repaired, "words", []):
            blocked += 1
        else:
            shape += 1
    return (f"word detector: {kept + blocked + shape} offered, {kept} accepted, "
            f"{blocked} blocked by an earlier region, {shape} refused on shape")


def lines_near(page, y: float, span: float = 26.0) -> None:
    """The baselines the detector built around this y, and why they broke.

    Every word table found on the real pages is exactly two rows tall, in every
    document, while the tables print three. Whether the third line is missing,
    or has too few cells, or fails to align, or sits too far below, decides
    which of four constants is wrong - and no amount of staring at the accepted
    output distinguishes them."""
    from tablerag.ingestion.word_tables import (
        _vertically_adjacent,
        column_bands,
        edges_align,
        group_lines,
        split_cells,
    )

    bands = column_bands(page.get_text("words"))
    print(f"{'':16} {'':8}   page splits into {len(bands)} band(s)")
    for b, band in enumerate(bands):
        near = [w for w in band if y - span <= (w[1] + w[3]) / 2 <= y + span]
        if not near:
            continue
        print(f"{'':16} {'':8}   band {b} x=[{min(w[0] for w in band):.0f},"
              f"{max(w[2] for w in band):.0f}]")
        previous = None
        for raw in group_lines(near):
            line = split_cells(raw)
            why = "first"
            if previous is not None:
                why = "ALIGNED" if edges_align(previous, line) else "not aligned"
                if not _vertically_adjacent(previous, line):
                    why += " + too far below"
            cells = [t[:14] for _, _, t in line.cells]
            print(f"{'':16} {'':8}     y={line.top:6.1f} cells={len(line.cells):2d} "
                  f"{why:22} {cells}")
            previous = line


def grade(item: dict, grids: list) -> tuple[bool, str]:
    found = len(grids)
    missing = [v for v in item.get("must_reach", []) if not reachable(grids, v)]
    if missing:
        return False, (f"{found}/{item['tables']} tables; "
                       f"unreachable: {', '.join(missing)}")
    return True, f"{found}/{item['tables']} tables; all values reachable"


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=here / "detection.jsonl")
    ap.add_argument("--pdf-dir", type=Path, default=here / "pdfs")
    ap.add_argument("--dump", action="store_true",
                    help="for each failing page, print the accepted regions and "
                         "where each unreachable value actually sits")
    ap.add_argument("--lines", action="store_true",
                    help="with --dump, also print the baselines the word "
                         "detector built around each missing value")
    args = ap.parse_args()

    items = [json.loads(line) for line in
             args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"{'id':16} {'verdict':8} detail")
    print("-" * 78)
    passed = ran = 0
    for item in items:
        path = args.pdf_dir / item["pdf"]
        if not path.exists():
            print(f"{item['id']:16} {'SKIP':8} not in {args.pdf_dir}: {item['pdf']}")
            continue
        ran += 1
        with fitz.open(path) as doc:
            page = doc[item["page"] - 1]
            found = detect_tables(page)
            ok, detail = grade(item, [grid for _, grid in found])
            passed += ok
            print(f"{item['id']:16} {'PASS' if ok else 'FAIL':8} {detail}")
            if not ok and item.get("note"):
                print(f"{'':16} {'':8} {item['note']}")
            if args.dump and not ok:
                print(f"{'':16} {'':8} {proposals(page, found)}")
                dump(page, item, found)
                if args.lines:
                    grids = [g for _, g in found]
                    seen: set[int] = set()
                    for value in item.get("must_reach", []):
                        if reachable(grids, value):
                            continue
                        for _, y0, _, _ in where(page.get_text("words"), value)[:1]:
                            if any(abs(y0 - s) < 20 for s in seen):
                                continue
                            seen.add(y0)
                            print(f"{'':16} {'':8}   --- lines around {value!r} "
                                  f"at y={y0} ---")
                            lines_near(page, float(y0))

    print("-" * 78)
    if not ran:
        print(f"nothing ran — drop the PDFs into {args.pdf_dir}")
        raise SystemExit(1)
    pct = 100 * passed / ran
    print(f"pages where every value is reachable: {passed}/{ran} = {pct:.0f}% "
          f"(target >= 95%: {'PASS' if pct >= 95 else 'FAIL'})")
    raise SystemExit(0 if pct >= 95 else 1)


if __name__ == "__main__":
    main()

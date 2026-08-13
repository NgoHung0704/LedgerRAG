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


def proposals(page) -> tuple[int, int]:
    """How many regions the word detector offered, and how many survived
    acceptance — the difference is accept_table's doing, not the detector's."""
    from tablerag.ingestion.layout import accept_table, repair_grid
    from tablerag.ingestion.word_tables import find_word_tables

    offered = find_word_tables(page.get_text("words"))
    kept = sum(1 for bbox, grid in offered
               if accept_table(fitz.Rect(bbox), repair_grid(grid), "words", []))
    return len(offered), kept


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
                offered, kept = proposals(page)
                print(f"{'':16} {'':8} word detector offered {offered}, "
                      f"{kept} pass acceptance")
                dump(page, item, found)

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

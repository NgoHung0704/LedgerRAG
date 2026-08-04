"""`make eval-figures` — the figure-reading gate.

A chart is the one thing in a document with no text to fall back on: its
labels are usually outlined, so nothing but a model can read them, and nothing
but the drawing can say whether the reading was right. This measures both
halves of that, against charts whose printed values were checked by hand.

Three scores, and they answer different questions:

  values   — of the numbers printed on the chart, how many does the
             description actually contain? (missing data)
  phantom  — numbers stated for a chart that prints NONE. A line chart with an
             unlabelled curve must be described without values; inventing one
             is the failure this whole feature is built to prevent, so the
             target is zero and nothing else will do.
  kind     — is a logo judged decorative and a chart judged informative? A
             wrong call here either floods the index with letterheads or drops
             a chart out of it entirely.

The geometric agreement is reported alongside — not as a score of the model,
but so a run says whether the check itself still separates good from bad.

    python tests/eval/figures/run_eval_figures.py [--pdf-dir DIR]
                                                  [--questions FILE]

Needs a live parser endpoint (the `parser` model role). The PDFs are not in
the repository — they are the operator's own documents; point --pdf-dir at
them, and see figures.jsonl for the ground truth format.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tablerag.ingestion.chart_check import (  # noqa: E402
    agreement,
    read_numbers,
)
from tablerag.ingestion.layout import analyze_document, crop_region_png  # noqa: E402
from tablerag.ingestion.ocr import describe_figure  # noqa: E402

TOLERANCE = 0.001   # a value counts as present if a read number matches it


def figures_of(pdf: Path, page: int) -> list:
    """Every figure region ingestion finds on one page, in reading order."""
    layouts = analyze_document(pdf.read_bytes(), dpi=120, min_chars=32)
    for layout in layouts:
        if layout.page == page:
            return [(layout, r) for r in layout.regions if r.type == "figure"]
    return []


def present(value: float, read: list[float]) -> bool:
    return any(abs(value - r) <= TOLERANCE for r in read)


def grade(item: dict, description: str, informative: bool,
          bars: list[float]) -> dict:
    read = read_numbers(description)
    expected = item.get("values", [])

    # a value may legitimately appear twice on a chart; consume matches so a
    # single read number cannot satisfy two printed ones
    free = list(read)
    found = 0
    for value in expected:
        match = next((r for r in free if abs(r - value) <= TOLERANCE), None)
        if match is not None:
            free.remove(match)
            found += 1

    phantom = 0
    if not item.get("labelled", True):
        # Nothing is printed on this chart, so a number offered as a DATA
        # value is invented. Only numbers inside the plotted range count: a
        # description names dates and axis bounds too, and counting those made
        # the one description that correctly refused to state a value look
        # like the worst offender in the set.
        #
        # Known blind spot: an invented value landing exactly on a tick is not
        # caught. Nothing in the geometry can separate the two.
        low, high = item.get("range", [None, None])
        ticks = item.get("axis", [])
        if low is not None:
            phantom = sum(1 for r in read
                          if low <= r <= high and not present(r, ticks))

    score, note = agreement(bars, read) if bars else (None, "no bars")
    return {
        "values": found / len(expected) if expected else None,
        "missing": [v for v in expected
                    if not present(v, read)] if expected else [],
        "phantom": phantom,
        "kind_ok": informative == item.get("informative", True),
        "agreement": score,
        "note": note,
    }


async def run(item: dict, pdf_dir: Path) -> dict:
    pdf = pdf_dir / item["pdf"]
    if not pdf.exists():
        return {"error": f"{pdf} not found"}
    # exists but unreadable is the likelier accident — a half-finished copy,
    # or an API error page saved under a .pdf name
    head = pdf.read_bytes()[:5]
    if head != b"%PDF-":
        return {"error": f"{pdf.name} is {pdf.stat().st_size} bytes and does "
                         f"not start with %PDF- (got {head!r}) — the copy did "
                         f"not finish, or this is not a PDF"}
    found = figures_of(pdf, item["page"])
    index = item.get("index", 0)
    if index >= len(found):
        return {"error": f"page {item['page']} has {len(found)} figure(s), "
                         f"wanted #{index} — detection regressed"}
    layout, region = found[index]
    crop = crop_region_png(layout.image_png, layout.width, region.bbox)
    description, informative = await describe_figure(
        crop, region.caption, region.groups)
    result = grade(item, description, informative, region.bars)
    result["description"] = description
    result["groups_measured"] = region.groups
    return result


def main() -> None:
    here = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, default=here / "figures.jsonl")
    ap.add_argument("--pdf-dir", type=Path, default=here / "pdfs")
    args = ap.parse_args()

    if not args.questions.exists():
        sys.exit(f"{args.questions} not found")
    items = [json.loads(line) for line in
             args.questions.read_text(encoding="utf-8").splitlines()
             if line.strip()]

    rows, errors, transcript = [], [], []
    print(f"{'id':22s} {'values':>7s} {'phantom':>7s} {'kind':>5s} "
          f"{'agree':>6s}  detail")
    print("-" * 78)
    for item in items:
        try:
            result = asyncio.run(run(item, args.pdf_dir))
        except Exception as e:  # noqa: BLE001
            result = {"error": str(e)}
        transcript.append({**item, **result})
        if "error" in result:
            # an item that could not RUN is not an item the model got wrong.
            # Folding it into the scores reported a broken input as "7
            # invented values", which is the gate lying about the pipeline.
            print(f"{item['id']:22s} {'ERROR':>7s} — {result['error']}")
            errors.append(item["id"])
            continue
        rows.append(result)
        values = ("  —  " if result["values"] is None
                  else f"{result['values']:6.0%}")
        agree = ("  —  " if result["agreement"] is None
                 else f"{result['agreement']:5.2f}")
        print(f"{item['id']:22s} {values:>7s} {result['phantom']:>7d} "
              f"{'ok' if result['kind_ok'] else 'WRONG':>5s} {agree:>6s}  "
              f"{result['note']}")
        if result["missing"]:
            print(f"{'':22s} missing: {result['missing']}")

    out = here / "results" / "last_run.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(json.dumps(t, ensure_ascii=False)
                             for t in transcript), encoding="utf-8")
    print(f"\nfull transcript: {out}")

    scored = [r for r in rows if r.get("values") is not None]
    value_rate = (sum(r["values"] for r in scored) / len(scored)
                  if scored else 1.0)
    phantoms = sum(r["phantom"] for r in rows)
    kinds = sum(1 for r in rows if r["kind_ok"]) / len(rows) if rows else 1.0

    print("-" * 78)
    if errors:
        print(f"NOT RUN: {len(errors)}/{len(items)} — {', '.join(errors)}")
    if not rows:
        # printing three PASS lines under "nothing ran" is how a gate comes to
        # be believed when it has measured nothing at all
        print("Nothing was measured. No score is reported.")
        sys.exit(1)
    if errors:
        print("The scores below cover only what ran.")
    verdicts = [
        ("values ", value_rate, 0.95, f"{value_rate:.0%}"),
        ("phantom", 1.0 if phantoms == 0 else 0.0, 1.0,
         f"{phantoms} invented"),
        ("kind   ", kinds, 1.0, f"{kinds:.0%}"),
    ]
    failed = bool(errors)
    for name, score, target, shown in verdicts:
        ok = score >= target
        failed |= not ok
        print(f"{name}: {shown:>14s}  (target >= {target:.0%}: "
              f"{'PASS' if ok else 'FAIL'})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

"""Scaffold a ground_truth.json for a REAL document table, to add it to the
spike eval set. This is the fast path from a production PDF to a gradable case.

The synthetic set (make_test_tables.py) is a clean lower bound. What actually
decides the parser is how it reads YOUR documents — a French livret du salarié,
a job-classification grid, a salary scale. Add 2-3 of those here before signing
off Phase 0 (SPEC recommends real scans before concluding).

Getting the table image:
  --image crop.png                 an already-cropped table image
  --pdf doc.pdf --page 4           render a PDF page to PNG
       [--bbox x0,y0,x1,y1]        crop a region of that page (PDF points)
       [--dpi 150]

Then it writes  spike/tables/<id>/image.png  and a  ground_truth.json  you edit.

  --prefill    first run the configured parser and drop the model's OWN reading
               into the records as a DRAFT. Correct the wrong cells instead of
               typing everything (much faster). The draft is a guess, not truth
               — verify every number against the image, then remove the "_draft"
               flag. grade.py refuses to score a table while "_draft" is true,
               so you can't accidentally grade the model against itself.

Example:
  python spike/make_gt_template.py --id livret_salarie \\
      --pdf livret.pdf --page 12 --locale fr --prefill
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))


def render_pdf_page(pdf_path: Path, page_num: int, dpi: int,
                    bbox: tuple[float, float, float, float] | None) -> bytes:
    import fitz  # PyMuPDF (already a platform dependency)

    with fitz.open(pdf_path) as doc:
        if not (1 <= page_num <= doc.page_count):
            raise SystemExit(f"page {page_num} out of range (1..{doc.page_count})")
        page = doc[page_num - 1]
        clip = fitz.Rect(*bbox) if bbox else None
        return page.get_pixmap(dpi=dpi, clip=clip).tobytes("png")


def skeleton_records() -> list[dict]:
    return [{
        "dimensions": {"<dimension_name>": "<value as string>"},
        "metrics": {"<metric_name>": 0},
        "raw_values": {"<metric_name>": "<exact string as printed in the image>"},
    }]


def scaffold(table_id: str, image_bytes: bytes, locale: str, difficulty: str,
             description: str, records: list[dict], is_draft: bool,
             tables_root: Path | None = None) -> Path:
    """Write image.png + ground_truth.json under tables_root/<id>/. Testable
    core (no CLI, no network)."""
    root = tables_root or (SPIKE_DIR / "tables")
    out_dir = root / table_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "image.png").write_bytes(image_bytes)

    gt: dict = {
        "table_id": table_id,
        "locale": locale,
        "difficulty": difficulty,
        "description": description,
    }
    if is_draft:
        gt["_draft"] = True
        gt["_instructions"] = (
            "This records array is the parser's OWN draft reading. Verify EVERY "
            "value against image.png, fix the wrong cells, then delete this "
            "\"_instructions\" field and set \"_draft\": false so grade.py will "
            "score it.")
    gt["records"] = records
    (out_dir / "ground_truth.json").write_text(
        json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="folder name under spike/tables/")
    ap.add_argument("--image", type=Path, help="pre-cropped table image")
    ap.add_argument("--pdf", type=Path, help="render a page from this PDF instead")
    ap.add_argument("--page", type=int, help="1-based page number (with --pdf)")
    ap.add_argument("--bbox", help="crop region 'x0,y0,x1,y1' in PDF points (with --pdf)")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--locale", default="fr", help="number locale hint (fr/de/en/es/...)")
    ap.add_argument("--difficulty", default="real")
    ap.add_argument("--description", default="Real document table — verify every cell")
    ap.add_argument("--prefill", action="store_true",
                    help="run the parser for a draft to correct by hand")
    # parser endpoint (only used with --prefill); same env as parse_table.py
    import parse_table
    ap.add_argument("--provider",
                    default=parse_table.env("LEDGERRAG_MODELS__PARSER__PROVIDER", "ollama"))
    ap.add_argument("--base-url",
                    default=parse_table.env("LEDGERRAG_MODELS__PARSER__BASE_URL",
                                            "http://localhost:11434"))
    ap.add_argument("--model",
                    default=parse_table.env("LEDGERRAG_MODELS__PARSER__MODEL_NAME",
                                            "qwen3-vl:8b-instruct"))
    args = ap.parse_args()

    if args.image:
        image_bytes = args.image.read_bytes()
    elif args.pdf:
        if not args.page:
            ap.error("--pdf requires --page")
        bbox = tuple(float(x) for x in args.bbox.split(",")) if args.bbox else None
        if bbox and len(bbox) != 4:
            ap.error("--bbox must be 'x0,y0,x1,y1'")
        image_bytes = render_pdf_page(args.pdf, args.page, args.dpi, bbox)
    else:
        ap.error("provide --image PATH or --pdf PATH --page N")

    records = skeleton_records()
    is_draft = False
    if args.prefill:
        out_dir = SPIKE_DIR / "tables" / args.id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "image.png").write_bytes(image_bytes)  # parse_one reads from here
        print(f"prefill: parsing with {args.provider} @ {args.base_url} "
              f"model={args.model} ...")
        result = parse_table.parse_one(out_dir / "image.png", args.provider,
                                       args.base_url, args.model, args.locale)
        if "error" not in result and result.get("records"):
            records = result["records"]
            is_draft = True
        else:
            print("  prefill failed to produce records — writing a blank skeleton "
                  "instead; fill it in by hand.")

    out_dir = scaffold(args.id, image_bytes, args.locale, args.difficulty,
                       args.description, records, is_draft)
    print(f"\nwrote {out_dir / 'image.png'}")
    print(f"wrote {out_dir / 'ground_truth.json'}"
          f"{'  (DRAFT — correct every cell, then set _draft=false)' if is_draft else ''}")
    print("\nNext: edit ground_truth.json to match the image, then:")
    print("  python spike/parse_table.py "
          f"--image {out_dir / 'image.png'} --model {args.model} "
          f"--base-url {args.base_url}")
    print("  python spike/grade.py")


if __name__ == "__main__":
    main()

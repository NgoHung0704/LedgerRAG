"""Generate deliberately-degraded table images for the Phase 3 flag eval.

Takes rendered tables from spike/tables/ and produces corrupted variants
(blur, low resolution, speckle noise, rotation) under spike/tables_hard/.
Ground truth copies the source records with "expect_flag": true — the
confidence layer is graded on flagging these (recall) without flagging the
clean originals (precision). See tests/eval/tables/run_flag_eval.py.

Usage:  python spike/make_hard_tables.py   (run make_test_tables.py first)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageFilter

TABLES_DIR = Path(__file__).parent / "tables"
HARD_DIR = Path(__file__).parent / "tables_hard"

# sources chosen to span difficulty; corrupt the hard ones AND an easy one
SOURCES = ["pivot_fr_auto", "totals_fr", "twolevel_fr_effectifs", "flat_fr_conges"]


def blur(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius=1.8))


def lowres(img: Image.Image) -> Image.Image:
    small = img.resize((int(img.width * 0.4), int(img.height * 0.4)),
                       Image.BILINEAR)
    return small.resize(img.size, Image.BILINEAR)


def noise(img: Image.Image) -> Image.Image:
    rng = random.Random(42)  # deterministic test set
    out = img.convert("RGB").copy()
    pixels = out.load()
    n_speckles = (out.width * out.height) // 60
    for _ in range(n_speckles):
        x, y = rng.randrange(out.width), rng.randrange(out.height)
        value = rng.choice([0, 255])
        pixels[x, y] = (value, value, value)
    return out.filter(ImageFilter.GaussianBlur(radius=0.6))


def rotate(img: Image.Image) -> Image.Image:
    return img.convert("RGB").rotate(2.5, expand=True, fillcolor="white",
                                     resample=Image.BICUBIC)


VARIANTS = {"blur": blur, "lowres": lowres, "noise": noise, "rotate": rotate}


def main() -> None:
    made = 0
    for source in SOURCES:
        src_dir = TABLES_DIR / source
        if not (src_dir / "image.png").exists():
            print(f"  {source}: missing — run make_test_tables.py first")
            continue
        gt = json.loads((src_dir / "ground_truth.json").read_text(encoding="utf-8"))
        with Image.open(src_dir / "image.png") as img:
            for name, transform in VARIANTS.items():
                out_dir = HARD_DIR / f"{source}__{name}"
                out_dir.mkdir(parents=True, exist_ok=True)
                transform(img).save(out_dir / "image.png")
                hard_gt = {**gt,
                           "table_id": f"{source}__{name}",
                           "difficulty": "corrupted",
                           "expect_flag": True,
                           "description": f"{name} variant of {source} — the "
                                          f"confidence layer should flag this"}
                (out_dir / "ground_truth.json").write_text(
                    json.dumps(hard_gt, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                made += 1
                print(f"  {source}__{name}")
    print(f"\nGenerated {made} corrupted tables -> {HARD_DIR}")


if __name__ == "__main__":
    main()

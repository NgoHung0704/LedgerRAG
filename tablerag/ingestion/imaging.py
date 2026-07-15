"""Small image helpers for the VLM input path (SPEC Phase 2 §6: light
upscale/denoise for low-quality inputs)."""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError


def crop_fraction(png_bytes: bytes,
                  box: tuple[float, float, float, float],
                  pad: float = 0.012) -> bytes:
    """Crop a region given as fractions of the image (0-1), with a little
    padding. Used to cut VLM-detected table regions out of a scanned page."""
    x0, y0, x1, y1 = box
    try:
        img_ctx = Image.open(io.BytesIO(png_bytes))
    except UnidentifiedImageError:
        return png_bytes
    with img_ctx as img:
        w, h = img.width, img.height
        px0 = max(0, int((x0 - pad) * w))
        py0 = max(0, int((y0 - pad) * h))
        px1 = min(w, int((x1 + pad) * w))
        py1 = min(h, int((y1 + pad) * h))
        if px1 <= px0 or py1 <= py0:
            return png_bytes
        out = io.BytesIO()
        img.crop((px0, py0, px1, py1)).save(out, format="PNG")
        return out.getvalue()


def ensure_min_width(png_bytes: bytes, min_width: int = 1400) -> bytes:
    """Upscale (LANCZOS) so the VLM never reads a table below `min_width` px.
    Real re-rendering at higher DPI is preferred where possible (text-layer
    tables); this is the fallback for scans and pre-rendered images.
    Unreadable bytes pass through untouched — the resizer must never be the
    crash point; a genuinely broken image fails visibly at the VLM instead."""
    try:
        img_ctx = Image.open(io.BytesIO(png_bytes))
    except UnidentifiedImageError:
        return png_bytes
    with img_ctx as img:
        if img.width >= min_width:
            return png_bytes
        scale = min_width / img.width
        resized = img.resize((min_width, round(img.height * scale)),
                             Image.LANCZOS)
        out = io.BytesIO()
        resized.save(out, format="PNG")
        return out.getvalue()

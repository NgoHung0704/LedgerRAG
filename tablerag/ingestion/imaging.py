"""Small image helpers for the VLM input path (SPEC Phase 2 §6: light
upscale/denoise for low-quality inputs)."""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError


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

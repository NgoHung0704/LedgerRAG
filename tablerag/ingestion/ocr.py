"""Scanned-page OCR via the parser VLM (SPEC Phase 2 §6: scans are not a
special case, just lower-quality image input to the same VLM).

The transcription prompt also asks for a machine-readable last line flagging
whether the page contains data tables, so the pipeline only spends a table
parse on scan pages that need one.
"""

from __future__ import annotations

import base64
import re

from tablerag.models.base import Msg
from tablerag.models.registry import get_provider

_OCR_PROMPT = """\
Transcribe ALL text content of this scanned page image, in natural reading \
order. Preserve paragraph breaks. Do not translate, summarize or comment.

After the transcription, output exactly one final line:
TABLES_PRESENT: yes
or
TABLES_PRESENT: no
depending on whether the page contains one or more data tables (grids of \
values). Lists and forms are not tables.\
"""

_FLAG_RE = re.compile(r"TABLES_PRESENT:\s*(yes|no)\s*$", re.IGNORECASE)


async def ocr_page(image_png: bytes) -> tuple[str, bool]:
    """Returns (transcribed_text, tables_present)."""
    from tablerag.core.config import get_settings

    parser = get_provider("parser")
    image_b64 = base64.b64encode(image_png).decode()
    s = get_settings()
    # full-page transcription needs the same large context as table parsing
    options = {"temperature": 0.0, "seed": s.table_parse_seed,
               "num_ctx": s.table_parse_num_ctx, "num_predict": s.table_parse_num_predict}
    parts = []
    async for token in parser.chat(
            [Msg(role="user", content=_OCR_PROMPT, images=[image_b64])],
            stream=True, temperature=0.0, options=options):
        parts.append(token)
    text = "".join(parts).strip()

    tables_present = False
    match = _FLAG_RE.search(text)
    if match:
        tables_present = match.group(1).lower() == "yes"
        text = text[:match.start()].rstrip()
    return text, tables_present

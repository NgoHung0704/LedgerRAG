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

# Re-reading a layout-heavy page (a slide, a process diagram, a comparison
# grid). Linear extraction flattens such a page row by row and destroys which
# heading each item belongs to; only a structured transcription keeps it, so the
# prompt's whole job is to preserve the 2-D relationships.
_STRUCTURED_PROMPT = """\
Transcribe this page faithfully, PRESERVING ITS STRUCTURE.

- If the content is laid out as a grid, as columns, or as a sequence of steps \
(a process diagram, a comparison, a matrix), render it as a MARKDOWN TABLE, so \
that everything belonging to one column or one step stays together with its \
heading. Use the headings shown on the page as the table's headers.
- If an arrow or a flow connects items, keep that order in the table's rows or \
columns, and state the relation in a short line under the table.
- Otherwise, transcribe as prose, using markdown headings and bullet lists as \
they appear.
- Copy every word, number and unit EXACTLY as printed. Never translate, \
summarize, complete or invent anything. If something is unreadable, write [?].
- Output only the transcription — no preamble, no commentary.\
"""


async def _transcribe(image_png: bytes, prompt: str) -> str:
    from tablerag.core.config import get_settings

    parser = get_provider("parser")
    image_b64 = base64.b64encode(image_png).decode()
    s = get_settings()
    # full-page transcription needs the same large context as table parsing
    options = {"temperature": 0.0, "seed": s.table_parse_seed,
               "num_ctx": s.table_parse_num_ctx, "num_predict": s.table_parse_num_predict}
    parts = []
    async for token in parser.chat(
            [Msg(role="user", content=prompt, images=[image_b64])],
            stream=True, temperature=0.0, options=options):
        parts.append(token)
    return "".join(parts).strip()


async def reread_page_structured(image_png: bytes) -> str:
    """Re-read a layout-heavy page into a structured transcription (a markdown
    table for a grid/diagram). Proposed to a human for review — never written
    straight over the extracted text."""
    return await _transcribe(image_png, _STRUCTURED_PROMPT)


async def ocr_page(image_png: bytes) -> tuple[str, bool]:
    """Returns (transcribed_text, tables_present)."""
    text = await _transcribe(image_png, _OCR_PROMPT)

    tables_present = False
    match = _FLAG_RE.search(text)
    if match:
        tables_present = match.group(1).lower() == "yes"
        text = text[:match.start()].rstrip()
    return text, tables_present

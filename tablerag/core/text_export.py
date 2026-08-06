"""Everything ingestion produced for one document, as plain text.

For showing someone — including whoever is going to fix it — exactly what came
out. So it holds the RAW forms, not the readable ones: a table's HTML as
stored, its records as JSON, a figure's measured palette, and above all the
chunks as they went into the index, because those are what retrieval actually
matches. A summary of a bad parse is not evidence of anything.

Formatting lives here rather than in the route so it can be tested without a
database, and reading it back is a diagnosis: element order is page order, and
every flag that changed a decision is printed beside the element it changed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

RULE = "=" * 78
THIN = "-" * 78


def _flags(element: dict) -> list[str]:
    """The decisions taken about this element, in the words used elsewhere."""
    out = []
    if element.get("needs_review"):
        out.append("NEEDS REVIEW")
    if element.get("unusable"):
        out.append("unusable (out of retrieval)")
    if element.get("edited"):
        out.append("edited by hand")
    if element.get("decorative"):
        out.append("decorative (described, not indexed)")
    if element.get("layout_suspect"):
        out.append("column layout — reading order not faithful")
    if element.get("ocr"):
        out.append("OCR (scanned page)")
    if element.get("vector"):
        out.append("vector drawing")
    if element.get("span_pages"):
        pages = ", ".join(str(p) for p in element["span_pages"])
        out.append(f"spans pages {pages}")
    return out


def _block(title: str, body: str | None) -> list[str]:
    if not body:
        return []
    return [f"--- {title} ---", body.rstrip(), ""]


def render(document: dict, elements: list[dict]) -> str:
    counts: dict[str, int] = {}
    for element in elements:
        counts[element["type"]] = counts.get(element["type"], 0) + 1
    shape = ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))

    lines = [
        "LedgerRAG — what ingestion produced for this document",
        f"document : {document.get('filename')}",
        f"status   : {document.get('status')} · "
        f"{document.get('page_count') or '?'} pages · "
        f"{len(elements)} elements ({shape or 'none'})",
        f"exported : {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "Chunks are shown exactly as indexed: that text, and nothing else, is",
        "what a question is matched against.",
        "",
    ]
    if document.get("error"):
        lines += [f"ingestion error: {document['error']}", ""]

    page = None
    for index, element in enumerate(elements, start=1):
        if element["page"] != page:
            page = element["page"]
            lines += [RULE, f"PAGE {page}", RULE, ""]

        bbox = element.get("bbox") or []
        where = (f"[{bbox[0]:.0f},{bbox[1]:.0f}] "
                 f"{bbox[2] - bbox[0]:.0f}x{bbox[3] - bbox[1]:.0f}"
                 if len(bbox) == 4 else "?")
        confidence = element.get("confidence")
        head = (f"[{index}] {element['type'].upper()}  page {element['page']}  "
                f"{where}  confidence "
                f"{'—' if confidence is None else f'{confidence:.2f}'}")
        lines += [THIN, head]
        for flag in _flags(element):
            lines.append(f"      ! {flag}")
        if element.get("context"):
            lines.append(f"      heading above: {element['context']}")
        if element.get("caption"):
            lines.append(f"      printed caption: {element['caption']}")
        if element.get("palette"):
            inks = ", ".join(f"{c['name']} ({c['hex']}, {c['share']:.0%})"
                             for c in element["palette"])
            lines.append(f"      colours measured: {inks}")
        if element.get("chart_check"):
            lines.append(f"      chart check: {element['chart_check']}")
        if element.get("parse_error"):
            lines.append(f"      parse error: {element['parse_error']}")
        lines.append("")

        lines += _block("description (parser model, not text from the page)",
                        element.get("description"))
        table = element.get("table")
        if table:
            shape_ = f"{table.get('n_rows') or '?'}x{table.get('n_cols') or '?'}"
            strategy = table.get("parse_strategy") or "?"
            lines += _block(f"html ({shape_}, {strategy})", table.get("html"))
            lines += _block("summary (routing)", table.get("summary"))
            records = table.get("records") or []
            if records:
                lines += _block(
                    f"records ({len(records)})",
                    json.dumps(records, ensure_ascii=False, indent=2))

        chunks = element.get("chunks") or []
        if chunks:
            body = "\n\n".join(f"[chunk {i}]\n{text}"
                               for i, text in enumerate(chunks, start=1))
            lines += _block(f"indexed text ({len(chunks)} chunk"
                            f"{'' if len(chunks) == 1 else 's'})", body)
        elif element["type"] != "table":
            lines += ["--- indexed text ---", "(nothing indexed)", ""]

    return "\n".join(lines) + "\n"

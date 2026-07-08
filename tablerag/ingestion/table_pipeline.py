"""Table sub-pipeline: one region -> the three representations (SPEC Phase 2).

1. `html`     — display
2. `records`  — dimensions/metrics/raw_values + text_repr, for exact lookup
3. `summary`  — one/two sentences for semantic routing

Two paths, chosen by the layout classifier: `simple_parser` (grid from the
PDF text layer, numbers normalized locale-aware) and `vlm` (the parser role).
Both end in the same TableResult; a VLM contract failure yields an honest
result (needs_review=True, salvaged html, no records) — never a crashed job.
"""

from __future__ import annotations

import html as html_mod
import logging
import re
from dataclasses import dataclass, field

from tablerag.core.numbers import parse_number
from tablerag.models.base import RecordParse, TableCtx
from tablerag.models.registry import get_provider

logger = logging.getLogger(__name__)

_SUMMARY_HTML_LIMIT = 4000
_NUMERIC_COLUMN_THRESHOLD = 0.7


@dataclass
class TableResult:
    html: str
    parse_strategy: str  # 'simple_parser' | 'vlm'
    n_rows: int | None = None
    n_cols: int | None = None
    summary: str | None = None
    needs_review: bool = False
    error: str | None = None
    records: list[dict] = field(default_factory=list)
    # each record: {dimensions, metrics, raw_values, text_repr}


def snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Zàâäéèêëîïôöùûüçñ]+", "_", str(name).strip().lower())
    return s.strip("_") or "col"


def build_text_repr(dimensions: dict, metrics: dict, raw_values: dict) -> str:
    """The embedded string, e.g.
    'Afrique | Algérie | Citadine | 2013 | T1 | janv. | chiffre_affaires: 7 462 639 | volume: 426'
    """
    dims = [str(v) for v in dimensions.values() if str(v).strip()]
    mets = []
    for key in metrics:
        shown = raw_values.get(key, metrics.get(key))
        mets.append(f"{key}: {shown}")
    return " | ".join(dims + mets)


def _grid_to_html(grid: list[list[str | None]]) -> str:
    rows = []
    for i, row in enumerate(grid):
        tag = "th" if i == 0 else "td"
        cells = "".join(
            f"<{tag}>{html_mod.escape(str(c).strip()) if c else ''}</{tag}>"
            for c in row)
        rows.append(f"  <tr>{cells}</tr>")
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def records_from_grid(grid: list[list[str | None]],
                      locale: str | None) -> list[dict]:
    """Simple path: header row + data rows. Columns whose values mostly parse
    as numbers become metrics (locale-aware, core/numbers.py); the rest are
    dimensions. raw strings are always preserved."""
    header = [str(h).strip() if h and str(h).strip() else f"col_{i}"
              for i, h in enumerate(grid[0])]
    keys = [snake(h) for h in header]
    data = grid[1:]

    numeric_cols: set[int] = set()
    for col in range(len(header)):
        values = [row[col] for row in data
                  if col < len(row) and row[col] and str(row[col]).strip()]
        if not values:
            continue
        parsed = [parse_number(str(v), locale) for v in values]
        if sum(p is not None for p in parsed) / len(values) >= _NUMERIC_COLUMN_THRESHOLD:
            numeric_cols.add(col)
    if len(numeric_cols) == len(header):  # keep at least one dimension
        numeric_cols.discard(0)

    records = []
    for row in data:
        dimensions, metrics, raw_values = {}, {}, {}
        for col, key in enumerate(keys):
            raw = str(row[col]).strip() if col < len(row) and row[col] else ""
            if col in numeric_cols:
                parsed = parse_number(raw, locale) if raw else None
                metrics[key] = parsed.value if parsed else None
                raw_values[key] = raw
            else:
                dimensions[key] = raw
        if not any(v is not None for v in metrics.values()) and not any(
                dimensions.values()):
            continue  # fully empty row
        records.append({
            "dimensions": dimensions, "metrics": metrics, "raw_values": raw_values,
            "text_repr": build_text_repr(dimensions, metrics, raw_values),
        })
    return records


def _records_from_vlm(parsed_records: list[RecordParse],
                      locale: str | None) -> list[dict]:
    records = []
    for rec in parsed_records:
        metrics = dict(rec.metrics)
        for key, value in metrics.items():
            if value is None and rec.raw_values.get(key):
                fallback = parse_number(str(rec.raw_values[key]), locale)
                if fallback is not None:
                    metrics[key] = fallback.value
        records.append({
            "dimensions": rec.dimensions, "metrics": metrics,
            "raw_values": rec.raw_values,
            "text_repr": build_text_repr(rec.dimensions, metrics, rec.raw_values),
        })
    return records


def _html_shape(html: str) -> tuple[int | None, int | None]:
    rows = re.findall(r"<tr[\s>]", html, re.IGNORECASE)
    cells = re.findall(r"<t[dh][\s>]", html, re.IGNORECASE)
    if not rows:
        return None, None
    return len(rows), max(1, round(len(cells) / len(rows)))


async def parse_table_region(crop_png: bytes, grid: list[list[str | None]] | None,
                             is_complex: bool, locale: str | None) -> TableResult:
    # --- simple path ---
    if grid and not is_complex:
        try:
            records = records_from_grid(grid, locale)
            if records:
                return TableResult(
                    html=_grid_to_html(grid), parse_strategy="simple_parser",
                    n_rows=len(grid), n_cols=len(grid[0]), records=records)
        except Exception:  # noqa: BLE001 — fall through to the VLM, never crash
            logger.exception("simple table path failed; falling back to VLM")

    # --- VLM path ---
    from tablerag.core.config import get_settings
    from tablerag.ingestion.imaging import ensure_min_width

    parser = get_provider("parser")
    vlm_image = ensure_min_width(crop_png,
                                 get_settings().vlm_min_image_width)
    parse = await parser.parse_table(
        vlm_image, TableCtx(locale_hint=locale or "unknown"))
    n_rows, n_cols = _html_shape(parse.html)
    if parse.error:
        # honest failure: keep the html/crop, flag for review, no records
        return TableResult(html=parse.html, parse_strategy="vlm",
                           n_rows=n_rows, n_cols=n_cols,
                           needs_review=True, error=parse.error)
    return TableResult(html=parse.html, parse_strategy="vlm",
                       n_rows=n_rows, n_cols=n_cols,
                       records=_records_from_vlm(parse.records, locale))


# language forcing: small chat models drift into their dominant training
# language (observed: Qwen emitting Persian/Chinese summaries for a French
# table). The declared KB locale pins the output language explicitly.
_LOCALE_LANGUAGE = {"fr": "French", "de": "German", "en": "English",
                    "es": "Spanish", "it": "Italian", "pt": "Portuguese"}

_SUMMARY_PROMPT = (
    "In one or two sentences, state what this table contains: subject, "
    "row/column dimensions, measures, period and units if visible.\n"
    "{language_rule}\n"
    "Output the summary sentence(s) only — no preamble, no other language, "
    "never mix languages.\n\n{html}")


def build_summary_prompt(html: str, locale: str | None) -> str:
    language = _LOCALE_LANGUAGE.get(locale or "")
    language_rule = (
        f"Write the summary in {language} ONLY."
        if language else
        "Write the summary in the dominant language of the table content ONLY.")
    return _SUMMARY_PROMPT.format(language_rule=language_rule,
                                  html=html[:_SUMMARY_HTML_LIMIT])


async def summarize_table(html: str, locale: str | None = None) -> str | None:
    """Representation 3 (semantic routing), generated by the chat role.
    Failure is tolerated: a table without a summary is still fully usable."""
    from tablerag.models.base import Msg

    if not html:
        return None
    try:
        chat = get_provider("chat")
        parts = []
        async for token in chat.chat(
                [Msg(role="user", content=build_summary_prompt(html, locale))],
                stream=True, temperature=0.0,
                options={"temperature": 0.0, "num_ctx": 4096}):
            parts.append(token)
        summary = "".join(parts).strip()
        return summary or None
    except Exception:  # noqa: BLE001
        logger.exception("table summary generation failed (non-fatal)")
        return None

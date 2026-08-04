"""VLM table-parsing contract: prompt + validation + retry, shared by every
provider (providers supply only their `chat` transport).

Promoted from spike/ (Phase 0 -> Phase 2, prompt v4). spike/prompts.py stays
as a standalone copy so the spike keeps working before the platform exists —
when iterating the prompt, change BOTH and re-run `make eval-tables`
(prompt is code, SPEC §5).
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from tablerag.models.base import Msg, RecordParse, TableCtx, TableParse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a precise document-table parser. You receive one image containing a \
single table and must transcribe it EXACTLY. You never invent, round, or \
"correct" values. If a cell is unreadable, you output null for its metric and \
keep whatever you could read in raw_values. Accuracy over completeness.\
"""

FEW_SHOT = """\
### Example 1 — flat table

Table (for illustration):
| Product | Units | Revenue    |
|---------|-------|------------|
| Alpha   | 1,240 | €52,300.50 |

Correct output:

```html
<table>
  <tr><th>Product</th><th>Units</th><th>Revenue</th></tr>
  <tr><td>Alpha</td><td>1,240</td><td>€52,300.50</td></tr>
</table>
```

```json
{"records": [
  {"dimensions": {"product": "Alpha"},
   "metrics": {"units": 1240, "revenue_eur": 52300.50},
   "raw_values": {"units": "1,240", "revenue_eur": "€52,300.50"}}
]}
```

### Example 2 — nested pivot with merged cells and measure groups

Table (for illustration): rows are Région > Pays (merged with rowspan). The \
column header has three stacked levels: "2013 T1" on top, then two measure \
groups "Chiffre d'affaires" and "Volume", then months "janv." / "févr." under \
each group.

Correct output:

```html
<table>
  <tr><th rowspan="3">Région</th><th rowspan="3">Pays</th><th colspan="4">2013 T1</th></tr>
  <tr><th colspan="2">Chiffre d'affaires</th><th colspan="2">Volume</th></tr>
  <tr><th>janv.</th><th>févr.</th><th>janv.</th><th>févr.</th></tr>
  <tr><td rowspan="2">Afrique</td><td>Algérie</td><td>7 462 639</td><td>6 990 210</td><td>426</td><td>401</td></tr>
  <tr><td>Maroc</td><td>5 240 880</td><td>5 102 300</td><td>301</td><td>295</td></tr>
</table>
```

```json
{"records": [
  {"dimensions": {"region": "Afrique", "pays": "Algérie", "annee": "2013", "trimestre": "T1", "mois": "janv."},
   "metrics": {"chiffre_affaires": 7462639, "volume": 426},
   "raw_values": {"chiffre_affaires": "7 462 639", "volume": "426"}},
  {"dimensions": {"region": "Afrique", "pays": "Algérie", "annee": "2013", "trimestre": "T1", "mois": "févr."},
   "metrics": {"chiffre_affaires": 6990210, "volume": 401},
   "raw_values": {"chiffre_affaires": "6 990 210", "volume": "401"}},
  {"dimensions": {"region": "Afrique", "pays": "Maroc", "annee": "2013", "trimestre": "T1", "mois": "janv."},
   "metrics": {"chiffre_affaires": 5240880, "volume": 301},
   "raw_values": {"chiffre_affaires": "5 240 880", "volume": "301"}},
  {"dimensions": {"region": "Afrique", "pays": "Maroc", "annee": "2013", "trimestre": "T1", "mois": "févr."},
   "metrics": {"chiffre_affaires": 5102300, "volume": 295},
   "raw_values": {"chiffre_affaires": "5 102 300", "volume": "295"}}
]}
```

Note in example 2: the header "2013 T1" produced BOTH "annee" and "trimestre"; \
each month is its own record; and chiffre_affaires + volume for the same \
coordinates live in the SAME record.
"""

INSTRUCTIONS = """\
Transcribe the table in the attached image. Reply with EXACTLY two fenced code \
blocks and nothing else:

1. A ```html block: the table as HTML using <table>/<tr>/<th>/<td>, reproducing \
merged cells with rowspan/colspan attributes. Cell text must be copied verbatim.

READING rule — merged (rowspan) cells: when a left-hand cell is merged across \
several rows, its label applies to EVERY spanned row, but each spanned row \
still has its OWN distinct values in the other columns. Read each data row \
independently, top to bottom; NEVER copy a value from one sub-row into another.

2. A ```json block: {"records": [...]} — one record per innermost data cell \
group, in LONG format. Three granularity rules, all mandatory:

RULE 1 — Keep every header level. Every column-header row above the value \
cells contributes to "dimensions", and header values are kept complete: a \
header "2013 T1" gives BOTH "2013" and "T1"; a year > quarter > month stack \
gives three entries. Never drop a level.

RULE 2 — Long format only. Time periods and categories from headers (T1, \
2023, janv., "Q1 2024", ...) are dimension VALUES, never metric key names.
WRONG: {"dimensions": {"poste": "Salaires"}, "metrics": {"t1": 812400, "t2": 824100}}
RIGHT: {"dimensions": {"poste": "Salaires", "periode": "T1"}, "metrics": {"montant": 812400}} \
plus a second record for T2, and so on.

RULE 3 — Measures share one record. Header levels that name a MEASURE \
(Revenue, Volume, Umsatz, Absatz, Chiffre d'affaires, Effectifs, ...) become \
the KEYS inside "metrics". All measures of the same coordinates go in the \
SAME record — never a "metric_type"-style dimension, never one record per \
measure.

Key naming: use header names as keys when the table names them; otherwise \
invent short consistent snake_case keys (e.g. "level_1"). Every record in one \
table must use the same dimension keys.

"metrics" values are UNQUOTED JSON numbers — dot as decimal separator, no \
thousands separators, no currency/unit symbols, never a string. A percentage \
like "12,5 %" becomes 12.5. Unreadable -> null.
"raw_values": the EXACT strings as printed in the image (same keys as metrics).

Number locale hint for this document: {locale_hint}. \
(fr: space-grouped thousands and comma decimals; de/es: dot thousands and comma \
decimals; en: comma thousands and dot decimals.)

Do not summarize, do not skip rows, do not add commentary.
"""

_FENCE_RE = re.compile(r"```(html|json)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

_GRID_HINT_TEMPLATE = """\
EXTRACTED CELL TEXT — this is the raw text of every cell, pulled directly from \
the document's text layer (one row per line, columns separated by " | ", a \
blank means the extractor found no text there). Use it like this:
- The VALUES are reliable: copy every number from this text, do NOT re-read \
digits from the image. If the text and the image seem to disagree on a value, \
trust the text.
- Row-merged group labels have ALREADY been repeated on every row they span in \
this text (a label like "H" covering two rows appears on both). Keep them \
repeated in your records — every spanned row carries the group label; do not \
collapse them back to one.
- A remaining blank cell is EITHER genuinely empty OR a column (colspan) \
continuation. Use the IMAGE to decide, and to attach every value to its correct \
row/column coordinates.
So: take the values from here, take the merge structure from the image.

{grid}
"""


# forward-fill of merged row labels: the VLM reads WHERE a merged group starts
# but often leaves the spanned rows blank (find_tables also leaves them blank).
# Propagating a short letter-label down its column reconstructs the rowspan
# deterministically — 100% where the model was ~90%. Guardrails keep it from
# filling legitimately-empty data cells (job titles, missing metrics).
_MERGE_LABEL_MAX_LEN = 4


def _is_propagatable_label(value: str, col: int) -> bool:
    """Column 0 is the leftmost dimension: a blank under a label there almost
    always means a merged continuation, so any-length labels propagate
    ('Fabrication', 'Maintenance'). Other columns only propagate short letter
    codes ('H', 'VIII') — never numbers (missing metrics) or long text
    (job titles like 'Directeur(trice)' above genuinely-empty cells)."""
    v = value.strip()
    if not v or not any(c.isalpha() for c in v):
        return False
    return col == 0 or len(v) <= _MERGE_LABEL_MAX_LEN


def forward_fill_grid(grid: list[list[str | None]]) -> list[list[str | None]]:
    """Propagate merged row labels downward into the blank cells below them,
    per column (reconstruct vertical rowspan merges). Guardrails: the header
    row (row 0) never propagates, leading blanks stay, numbers never fill —
    so genuinely-empty data cells are left alone (SPEC: never invent
    structure where there is none)."""
    if not grid:
        return grid
    n_cols = max((len(row) for row in grid), default=0)
    filled = [list(row) + [None] * (n_cols - len(row)) for row in grid]
    for c in range(n_cols):
        last: str | None = None
        for r in range(len(filled)):
            cell = filled[r][c]
            text = str(cell).strip() if cell not in (None, "") else ""
            if r == 0:
                last = None  # headers never propagate into data rows
            elif text:
                last = text if _is_propagatable_label(text, c) else None
            elif last is not None:
                filled[r][c] = last
    return filled


def format_grid_hint(grid: list[list[str | None]] | None,
                     max_chars: int = 3000) -> str | None:
    """Render a find_tables grid as a pipe-delimited hint, with merged row
    labels forward-filled so the VLM sees the propagated structure instead of
    ambiguous blanks."""
    if not grid:
        return None
    grid = forward_fill_grid(grid)

    def cell_text(cell) -> str:
        if not cell:
            return ""
        # in-cell line breaks would break the one-line-per-row format
        return "; ".join(p.strip() for p in str(cell).splitlines() if p.strip())

    lines = [" | ".join(cell_text(cell) for cell in row) for row in grid]
    text = "\n".join(lines).strip()
    return text[:max_chars] if text.replace("|", "").strip() else None


def build_user_prompt(locale_hint: str = "unknown",
                      grid_hint: str | None = None) -> str:
    prompt = FEW_SHOT + "\n" + INSTRUCTIONS.replace("{locale_hint}", locale_hint)
    if grid_hint:
        prompt += "\n\n" + _GRID_HINT_TEMPLATE.replace("{grid}", grid_hint)
    return prompt


def build_retry_prompt(error: str) -> str:
    return (
        "Your previous output could not be parsed. Error:\n"
        f"{error}\n\n"
        "Reply again with EXACTLY one ```html block and one ```json block "
        "following the contract. No other text."
    )


# Detection sometimes draws one region around two tables that happen to share a
# ruling or sit flush against each other. Read as one, their rows land in one
# set of records, and a question about the first table can be answered from a
# row of the second — the worst kind of wrong, because it looks right.
#
# The model is asked ONLY where the seam is, never to parse both: the split is
# a judgement it can make (a second header, a change of subject) and the
# parsing is left to the contract that has been measured.
SPLIT_PROMPT = """\
The rows below were read as ONE table. Decide whether they are really two or \
more tables printed one under another — a second table has its own header row \
and its own subject, not a continuation of the first.

Rows, numbered:
{rows}

Reply with exactly one line and nothing else:
SPLIT BEFORE ROWS: 7
listing the row number that STARTS each table after the first, separated by \
commas. If it is a single table, reply:
SPLIT BEFORE ROWS: none

A repeated header alone is not a split — a long table continuing on the same \
page may repeat its header. Split only when the SUBJECT changes.\
"""

_SPLIT_RE = re.compile(r"SPLIT\s+BEFORE\s+ROWS?\s*:\s*(.+)", re.IGNORECASE)


def numbered_rows(grid: list[list[str | None]], max_chars: int = 3000) -> str:
    """The grid as numbered lines, so a row number means the same thing to the
    model and to the caller that will cut the region at it."""
    lines = []
    for i, row in enumerate(grid, start=1):
        cells = "; ".join(" ".join(str(c or "").split()) for c in row)
        lines.append(f"{i}. {cells}")
    return "\n".join(lines)[:max_chars]


def parse_split_rows(text: str, n_rows: int) -> list[int]:
    """Row numbers (1-based) where a new table starts. Empty when there is no
    split, or when the answer names rows that cannot be seams."""
    match = _SPLIT_RE.search(text or "")
    if not match:
        return []
    answer = match.group(1).strip()
    if answer.lower().startswith("none"):
        return []
    rows = []
    for piece in re.split(r"[,\s]+", answer):
        try:
            row = int(piece)
        except ValueError:
            continue
        # row 1 is the start of the FIRST table, not a seam, and a seam past
        # the end would cut off nothing
        if 1 < row <= n_rows and row not in rows:
            rows.append(row)
    return sorted(rows)


class TableContractError(Exception):
    pass


def parse_response(text: str) -> tuple[str, list[dict]]:
    """Extract and validate the two fenced blocks. Raises TableContractError
    with a message specific enough to drive the retry prompt."""
    blocks = {kind.lower(): body for kind, body in _FENCE_RE.findall(text)}
    html = blocks.get("html", "").strip()
    if not html:
        raise TableContractError("missing ```html block")
    if "json" not in blocks:
        raise TableContractError("missing ```json block")
    try:
        payload = json.loads(blocks["json"])
    except json.JSONDecodeError as e:
        raise TableContractError(f"json block is not valid JSON: {e}") from e
    # the contract is {"records": [...]}, but a model sometimes emits the bare
    # array. That is the same data, so accept it rather than lose the table —
    # and never let an unexpected shape raise something other than
    # TableContractError (a raw AttributeError here used to escape the retry
    # path and fail the WHOLE document, e.g. a top-level JSON list).
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("records")
    else:
        raise TableContractError('json block must be {"records": [...]}')
    if not isinstance(records, list) or not records:
        raise TableContractError('json block must be {"records": [...]} with >= 1 record')
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise TableContractError(
                f"record {i} must be an object with 'dimensions', 'metrics' "
                f"and 'raw_values', got {type(rec).__name__}")
        for key in ("dimensions", "metrics", "raw_values"):
            if not isinstance(rec.get(key), dict):
                raise TableContractError(f"record {i}: '{key}' must be an object")
        for k, v in rec["metrics"].items():
            if v is not None and not isinstance(v, (int, float)):
                raise TableContractError(
                    f"record {i}: metric '{k}' must be a JSON number or null, got {v!r}")

    # dimension tuples must be UNIQUE: dimensions are a record's identity
    # (principle #2 — dims/metrics split), so two records sharing the same
    # dimensions means a header level was dropped. Measured on the box:
    # pivot_de_umsatz read every value perfectly but omitted the year level
    # -> 8 records in 4 indistinguishable pairs -> 0/16 despite perfect
    # numbers; twolevel_fr_effectifs relabelled R&D rows as an existing
    # service; pivot_fr_auto duplicated one modele's rows. All three leave
    # this exact fingerprint, none can be caught by value checks (the values
    # are right), and the retry prompt tells the model precisely what to add.
    seen_dims: dict[tuple, int] = {}
    for i, rec in enumerate(records):
        key = tuple(sorted((str(k), str(v)) for k, v in rec["dimensions"].items()))
        if key in seen_dims:
            dims = json.dumps(rec["dimensions"], ensure_ascii=False)
            raise TableContractError(
                f"records {seen_dims[key]} and {i} have IDENTICAL dimensions "
                f"{dims} — dimensions must uniquely identify each record. A "
                "header level that distinguishes them (a year, period, or "
                "category row above the values) is missing: re-read the "
                "column headers and include EVERY header level in the "
                "dimensions of EVERY record, and never emit the same row "
                "twice while skipping its sibling rows")
        seen_dims[key] = i
    return html, records


def salvage_html(text: str) -> str:
    """Best-effort html extraction for the honest-failure path."""
    blocks = {kind.lower(): body for kind, body in _FENCE_RE.findall(text)}
    return blocks.get("html", "").strip()


ChatFn = Callable[..., AsyncIterator[str]]


def parse_options(read_variant: int = 0) -> dict:
    """Generation options proven out in the Phase 0 spike. num_ctx large enough
    that the few-shot prompt + vision image never truncates (see SPEC/config).
    read_variant > 0 (Phase 3 double-read) shifts seed and adds a little
    temperature so the second read is an independent opinion."""
    from tablerag.core.config import get_settings

    s = get_settings()
    return {"temperature": 0.0 if read_variant == 0 else 0.2,
            "seed": s.table_parse_seed + read_variant,
            "num_ctx": s.table_parse_num_ctx,
            "num_predict": s.table_parse_num_predict}


async def _collect(chat: ChatFn, messages: list[Msg], options: dict) -> str:
    parts = []
    async for token in chat(messages, stream=True, temperature=0.0, options=options):
        parts.append(token)
    return "".join(parts)


# A second look that is given EVIDENCE rather than encouragement.
#
# Telling this model to "read more carefully" is the one thing measured to make
# it worse (RULE 4: 79.9% -> 75.1%, reverted). What measured BETTER was handing
# it something concrete to react to: the contract's duplicate-dims rejection,
# with the specific error, moved production 79.9% -> 88.4%. So the verification
# pass shows the model its own first reading and asks it to fault it against the
# image, cell by cell — and it answers under the SAME contract, so every
# structural guard still applies to the correction.
VERIFY_PROMPT = """\
You are CHECKING an existing transcription of the table in this image. Your job \
is to FIND WHAT IS WRONG WITH IT, and only then correct it.

Work in two steps, in this order.

STEP 1 — Fault it. Go cell by cell against the image and list every error you \
can actually point at. Write, on its own line each:
FINDINGS:
- row <n>, column "<header>": image shows "<what is printed>", reading says \
"<what the proposal has>" — <why it is wrong>
If, after checking every cell, you find nothing wrong, write exactly:
FINDINGS: none

STEP 2 — Correct ONLY what you listed in step 1. Every other cell must come \
back byte-for-byte identical, digit grouping and spacing included. If your \
findings were "none", return the reading completely unchanged.

You may not change anything you did not fault, you may not add a row, a column \
or a value that is not visible in the image, and you may not translate.

Check hardest where this kind of reading goes wrong:
- a merged cell whose value must repeat on EVERY row or column it covers;
- a header level dropped from the dimensions;
- a value that belongs one row or one column further along;
- digits that look alike (0/8, 1/7, 3/5, 6/5) and thousands separators.

After the findings, reply with the same two blocks as the proposal and nothing \
else: one ```html block, then one ```json block containing {"records": [...]}.\
"""


def build_verify_prompt(html: str, records: list[dict],
                        grid_hint: str | None = None) -> str:
    """The first reading, handed back for faulting — with the text-layer values
    alongside it when there are any: catching a misread digit is a comparison,
    not an act of attention."""
    payload = json.dumps({"records": records}, ensure_ascii=False, indent=1)
    parts = [VERIFY_PROMPT]
    if grid_hint:
        parts.append(_GRID_HINT_TEMPLATE.format(grid=grid_hint))
    parts.append(f"Reading to check:\n\n```html\n{html}\n```\n\n"
                 f"```json\n{payload}\n```")
    return "\n\n".join(parts)


_FINDINGS_NONE = re.compile(r"FINDINGS:\s*none\b", re.IGNORECASE)


def split_findings(text: str) -> tuple[str, bool]:
    """(what the check said it found, whether it claims the reading was clean).
    Everything before the first fenced block is the reasoning."""
    head = text.split("```", 1)[0].strip()
    return head, bool(_FINDINGS_NONE.search(head))


@dataclass
class TableVerification:
    """The outcome of checking a reading: what the model faulted, and the
    correction that follows from it."""

    parse: TableParse | None   # None when the check produced nothing usable
    findings: str = ""         # what it says is wrong, verbatim
    clean: bool = False        # it examined the reading and found no fault


async def run_table_verify(chat: ChatFn, image: bytes, ctx: TableCtx,
                           html: str, records: list[dict],
                           grid_hint: str | None = None) -> TableVerification:
    """Check a reading against the image: fault it first, then correct only what
    was faulted.

    A correction with no stated fault behind it is the failure mode to avoid —
    the model "improving" cells that were already right. Making it name the
    error first is what keeps the rewrite honest, and gives the reviewer the one
    thing they need: where to look."""
    image_b64 = base64.b64encode(image).decode()
    options = parse_options(0)  # the check itself is deterministic
    messages = [
        Msg(role="system", content=SYSTEM_PROMPT),
        Msg(role="user",
            content=build_verify_prompt(html, records, grid_hint),
            images=[image_b64]),
    ]
    text = await _collect(chat, messages, options)
    findings, clean = split_findings(text)
    try:
        new_html, new_records = _parse_or_contract_error(text)
    except TableContractError as first_error:
        retry = messages + [
            Msg(role="assistant", content=text),
            Msg(role="user", content=build_retry_prompt(str(first_error))),
        ]
        try:
            retried = await _collect(chat, retry, options)
            new_html, new_records = _parse_or_contract_error(retried)
            findings, clean = split_findings(retried) or (findings, clean)
        except TableContractError as second_error:
            logger.warning("verification pass violated the contract twice (%s)",
                           second_error)
            return TableVerification(parse=None, findings=findings, clean=clean)
    return TableVerification(
        parse=TableParse(html=new_html,
                         records=[RecordParse(**r) for r in new_records],
                         raw_response=text),
        findings=findings, clean=clean)


def _parse_or_contract_error(text: str) -> tuple[str, list[dict]]:
    """parse_response, with any unexpected exception recast as a contract
    violation. One malformed reply must cost ONE table (flagged, original image
    kept — SPEC §0.3 fail honestly), never the whole document: an escaping
    TypeError/AttributeError used to abort ingestion for every page."""
    try:
        return parse_response(text)
    except TableContractError:
        raise
    except Exception as e:  # noqa: BLE001 — defensive: unknown reply shape
        logger.warning("unexpected shape in table reply (%s: %s)",
                       type(e).__name__, e)
        raise TableContractError(
            f"unexpected {type(e).__name__} while reading the reply: {e}") from e


async def run_table_parse(chat: ChatFn, image: bytes, ctx: TableCtx) -> TableParse:
    """One parse attempt + one retry with the concrete error (SPEC Phase 2 §3).
    Never raises on contract failure — returns an honest TableParse.error."""
    image_b64 = base64.b64encode(image).decode()
    options = parse_options(ctx.read_variant)
    messages = [
        Msg(role="system", content=SYSTEM_PROMPT),
        Msg(role="user",
            content=build_user_prompt(ctx.locale_hint or "unknown", ctx.grid_hint),
            images=[image_b64]),
    ]
    text = await _collect(chat, messages, options)
    raw = text
    try:
        html, records = _parse_or_contract_error(text)
    except TableContractError as first_error:
        retry = messages + [
            Msg(role="assistant", content=text),
            Msg(role="user", content=build_retry_prompt(str(first_error))),
        ]
        text2 = await _collect(chat, retry, options)
        raw = f"{text}\n\n=== RETRY ===\n\n{text2}"
        try:
            html, records = _parse_or_contract_error(text2)
        except TableContractError as second_error:
            return TableParse(
                html=salvage_html(text2) or salvage_html(text), records=[],
                raw_response=raw,
                error=f"contract violation after retry: {second_error}")
    return TableParse(html=html,
                      records=[RecordParse(**r) for r in records],
                      raw_response=raw)

"""Prompts for the Phase 0 spike table parser.

Prompt is code (spec §5): any change here must be followed by re-running
`make spike-run && make spike-grade` and pasting results into the PR / REPORT.md.
"""

SYSTEM_PROMPT = """\
You are a precise document-table parser. You receive one image containing a \
single table and must transcribe it EXACTLY. You never invent, round, or \
"correct" values. If a cell is unreadable, you output null for its metric and \
keep whatever you could read in raw_values. Accuracy over completeness.\
"""

# Few-shot examples are textual (no images) on purpose: they teach the output
# CONTRACT, not the visual task. Example 1 = flat table, example 2 = nested pivot.
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

### Example 2 — nested pivot with merged cells

Table (for illustration): rows grouped as Région > Pays (merged with rowspan), \
columns grouped as year "2013" over months "janv." and "févr.", values are \
French-formatted revenue.

Correct output:

```html
<table>
  <tr><th rowspan="2">Région</th><th rowspan="2">Pays</th><th colspan="2">2013</th></tr>
  <tr><th>janv.</th><th>févr.</th></tr>
  <tr><td rowspan="2">Afrique</td><td>Algérie</td><td>7 462 639</td><td>6 990 210</td></tr>
  <tr><td>Maroc</td><td>5 240 880</td><td>5 102 300</td></tr>
</table>
```

```json
{"records": [
  {"dimensions": {"region": "Afrique", "pays": "Algérie", "annee": "2013", "mois": "janv."},
   "metrics": {"chiffre_affaires": 7462639},
   "raw_values": {"chiffre_affaires": "7 462 639"}},
  {"dimensions": {"region": "Afrique", "pays": "Algérie", "annee": "2013", "mois": "févr."},
   "metrics": {"chiffre_affaires": 6990210},
   "raw_values": {"chiffre_affaires": "6 990 210"}},
  {"dimensions": {"region": "Afrique", "pays": "Maroc", "annee": "2013", "mois": "janv."},
   "metrics": {"chiffre_affaires": 5240880},
   "raw_values": {"chiffre_affaires": "5 240 880"}},
  {"dimensions": {"region": "Afrique", "pays": "Maroc", "annee": "2013", "mois": "févr."},
   "metrics": {"chiffre_affaires": 5102300},
   "raw_values": {"chiffre_affaires": "5 102 300"}}
]}
```
"""

INSTRUCTIONS = """\
Transcribe the table in the attached image. Reply with EXACTLY two fenced code \
blocks and nothing else:

1. A ```html block: the table as HTML using <table>/<tr>/<th>/<td>, reproducing \
merged cells with rowspan/colspan attributes. Cell text must be copied verbatim.

2. A ```json block: {"records": [...]} — one record per INNERMOST data cell \
group. Granularity rules (critical):
   - If column headers are nested (e.g. a year spanning months), each innermost \
column produces its OWN record, and every header level above it becomes a \
dimension value on that record. In example 2 above: one record per (row, month), \
with the year AND the month both present as dimensions.
   - NEVER fold header values into metric key names ("revenue_jan" is WRONG — \
"jan" belongs in dimensions, the metric key is "revenue").
   - NEVER aggregate several columns or rows into one record.
   Each record has:
   - "dimensions": ALL row header values and ALL column header levels that \
locate the cell (as strings — split combined headers like "2013 T1" into their \
own entries when they are separate header cells). Use header names as keys when \
the table names them; otherwise invent short consistent snake_case keys \
(e.g. "level_1"). Every record in one table must use the same dimension keys.
   - "metrics": the numeric values as UNQUOTED JSON numbers — dot as decimal \
separator, no thousands separators, no currency/unit symbols, never a string. \
A percentage like "12,5 %" becomes 12.5. Unreadable -> null.
   - "raw_values": the EXACT strings as printed in the image (same keys as metrics).

Number locale hint for this document: {locale_hint}. \
(fr: space-grouped thousands and comma decimals; de/es: dot thousands and comma \
decimals; en: comma thousands and dot decimals.)

Do not summarize, do not skip rows, do not add commentary.
"""


def build_user_prompt(locale_hint: str = "unknown") -> str:
    return FEW_SHOT + "\n" + INSTRUCTIONS.replace("{locale_hint}", locale_hint)


def build_retry_prompt(error: str) -> str:
    return (
        "Your previous output could not be parsed. Error:\n"
        f"{error}\n\n"
        "Reply again with EXACTLY one ```html block and one ```json block "
        "following the contract. No other text."
    )

"""Prompts for the Phase 0 spike table parser.

Prompt is code (spec §5): any change here must be followed by re-running
`make spike-run && make spike-grade` and pasting results into the PR / REPORT.md.

Iteration history (see REPORT.md for full campaign results):
- v1: baseline contract. qwen2.5vl:7b ~5% — records matched nothing.
- v2: granularity rules v1. qwen3-vl:8b-instruct 45.5% — every NUMBER correct,
  all remaining misses were 3 structural motifs: (1) dropped header levels
  (trimestre/quarter), (2) wide format (periods as metric keys), (3) measures
  split into separate records via a metric_type dimension.
- v3: few-shot example 2 mirrors the hardest real shape (3-level header + two
  measure groups) and three granularity rules target the motifs directly.
  qwen3-vl:8b-instruct 84.1% — 10/12 tables 100%. Two residual failures:
  twolevel_fr (ground-truth orientation bug, fixed in the generator, not here)
  and pivot_fr_auto (a genuine READING error: values copied between sub-rows
  of a deep rowspan).
- v4 (current): adds an explicit rowspan reading rule aimed at the pivot_fr
  misread. This is a visual-alignment limit of the model, so the prompt may
  not fully fix it — if pivot_fr stays low, that is the honest model ceiling
  on the hardest table (exactly what Phase 3 confidence is built to catch).
"""

SYSTEM_PROMPT = """\
You are a precise document-table parser. You receive one image containing a \
single table and must transcribe it EXACTLY. You never invent, round, or \
"correct" values. If a cell is unreadable, you output null for its metric and \
keep whatever you could read in raw_values. Accuracy over completeness.\
"""

# Few-shot examples are textual (no images) on purpose: they teach the output
# CONTRACT, not the visual task. Example 1 = flat table, example 2 = nested
# pivot in exactly the shape that models get wrong (stacked column headers +
# measure groups + merged row cells).
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
independently, top to bottom; NEVER copy a value from one sub-row into \
another. (E.g. under a merged "Algérie", the "Citadine" row and the "Berline" \
row have different numbers — do not repeat Citadine's figures on Berline.)

2. A ```json block: {"records": [...]} — one record per innermost data cell \
group, in LONG format. Three granularity rules, all mandatory:

RULE 1 — Keep every header level. Every column-header row above the value \
cells contributes to "dimensions", and header values are kept complete: a \
header "2013 T1" gives BOTH "2013" and "T1" (e.g. {"annee": "2013", \
"trimestre": "T1"}); a year > quarter > month stack gives three entries. \
Never drop a level.

RULE 2 — Long format only. Time periods and categories from headers (T1, \
2023, janv., "Q1 2024", ...) are dimension VALUES, never metric key names.
WRONG: {"dimensions": {"poste": "Salaires"}, "metrics": {"t1": 812400, "t2": 824100}}
RIGHT: {"dimensions": {"poste": "Salaires", "periode": "T1"}, "metrics": {"montant": 812400}} \
plus a second record for T2, and so on.

RULE 3 — Measures share one record. Header levels that name a MEASURE \
(Revenue, Volume, Umsatz, Absatz, Chiffre d'affaires, Effectifs, ...) become \
the KEYS inside "metrics". All measures of the same coordinates go in the \
SAME record — never a "metric_type"-style dimension, never one record per \
measure (see example 2: chiffre_affaires and volume together).

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


def build_user_prompt(locale_hint: str = "unknown") -> str:
    return FEW_SHOT + "\n" + INSTRUCTIONS.replace("{locale_hint}", locale_hint)


def build_retry_prompt(error: str) -> str:
    return (
        "Your previous output could not be parsed. Error:\n"
        f"{error}\n\n"
        "Reply again with EXACTLY one ```html block and one ```json block "
        "following the contract. No other text."
    )

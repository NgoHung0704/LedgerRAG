# Answer completeness: what the gate said

Measured 2026-08-12 on MIA-82025, KB `2f41efdf` (PERCO), question set
`tests/eval/qa/funds.jsonl`, 17 questions over six EPSENS fund factsheets held
in three reporting editions each (30/09/2021, 31/08/2023, 30/09/2024).

Both runs share one environment: same image, same `qdrant-client` bound to the
pinned server, same corpus, taken minutes apart. An earlier baseline exists but
is **not comparable** — it predates the client bound, and comparing across a
retrieval-library change would attribute the library's behaviour to this work.

## The numbers

| | `expand_neighbours=false` | `expand_neighbours=true` |
|---|---|---|
| table | 3/8 (38%) | 3/8 (38%) |
| text  | 2/2 (100%) | 2/2 (100%) |
| trap  | **3/7 (43%)** | **1/7 (14%)** |

**Neighbour expansion is not kept.** It moved nothing on tables and destroyed
honest refusals. The default stays `False`.

## Why it hurt

`expand: 12 ranked hit(s) pulled in 43 neighbour(s)` — between 18 and 53 per
query. Citations went from 12 blocks to 52-54. In one answer a single document
appeared eight times.

Two traps flipped from PASS to FAIL, and both flipped the same way:

- **f10** asked for TRANSITION CLIMAT's 3-year volatility *in the 30/09/2021
  reporting*. That edition has no risk-indicator table, and with expansion off
  the assistant said so. With it on, expansion dragged in the **2024** edition's
  table and the assistant stated 17,73 % with confidence.
- **f11** asked a question naming no fund at all. Refused when off; answered
  -1,47 % from FLEXI when on.

Flooding the context with material from other funds and other periods turned
"not in the documents" into a number. That is the exact failure this work set
out to prevent, produced by the work itself.

## The design defect, precisely

The budget caps **characters**, not **count**. At
`(32768 - 3000) x 3 = 89,304` characters, 52 small chunks fit comfortably, so
`trim_to_budget` never fired and its careful sacrifice order never ran. Meanwhile
"every table and figure on the winner's page", applied to twelve winners spread
over twelve documents, has no upper bound at all.

A character budget does not constrain a feature whose damage is *dilution*
rather than *size*.

## What the overlap contrast did

`OVERLAP_RULE` ships with **no flag**, so it was active in both runs and cannot
be A/B tested. That is a design mistake in this plan: expansion got a flag and
overlap did not.

The logs show it firing on 15 of 17 queries, 1-2 groups each — and grouping the
wrong sources. On **f5**, the flagship case (asked for FLEXI's taux de sélection
SR, answered 83,27 % which is RHONE-ALPES's value), it grouped `[8+12]`: two
`Doc info clé` regulatory documents, near-identical because they follow a
mandated template. The pair that actually caused the error — `[2]` EPSENS FLEXI
and `[5]` EPSENS RHONE-ALPES — was never grouped.

The cause is structural: `group_overlapping` is **blind to the question**. It
groups any two similar sources in the context, so boilerplate documents that
always resemble each other always group, while the pair that differs on the
value being asked about goes unnoticed.

## The four failure modes, which are not one problem

Read against the source PDFs, the table failures have four distinct causes and
only two of them are addressed by anything in this plan:

| id | wrong answer | cause |
|---|---|---|
| f1 | 20,17 instead of 50,46 | the **1 an** column of the right row in the right table. Table reading. |
| f3 | 4,96 instead of 2,63 | cumulative-performance 3 ans instead of volatility 3 ans. Two tables sharing a "3 ans" header. |
| f5 | 83,27 instead of 44,20 | another fund's value. |
| f6 | 5,72 instead of 5,31 | another reporting period's value. |

f1 is a parsing/reading problem and no retrieval feature will touch it.

## Also found

`EPSENS MONETAIRE ISR - 4004.pdf` has no `Reporting au 30/09/2021` line in its
extracted text, so it cannot be found by date — f2's refusal is honest and
correct given what is indexed. The file is identifiable as the 2021 edition only
by its holdings maturities (02/02/2022, 08/04/2022, 09/05/2022, 10/03/2022),
which match that sheet's PRINCIPALES LIGNES exactly. An ingestion defect,
separate from this work.

## What would be worth trying next, and what would not

Not worth it: raising or lowering the character budget. The damage was dilution.

Worth one measurement each, separately:

1. **Cap the count.** Expand only the top few ranked hits, and cap total
   neighbours outright. The current rule multiplies twelve winners by a whole
   page each.
2. **Give the overlap grouping the question.** Group only sources that both
   plausibly answer what was asked, so two boilerplate DICs stop consuming the
   contrast rule while the real pair goes unflagged.
3. **Put a flag on the overlap contrast**, so it can be measured at all.

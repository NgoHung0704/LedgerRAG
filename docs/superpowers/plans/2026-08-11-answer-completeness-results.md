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


---

# Addendum: the reranker was the thing

Same day, same KB, same question set. Four defects had to be cleared before the
reranker ran at all, each of them silent:

1. a **database role override** pointing at a vLLM that no longer runs, beating
   the environment variables entirely (`/api/models` showed `overridden: true`,
   `"All connection attempts failed"`);
2. a **health probe** on `/v1/models`, a path TEI does not serve, painting a
   working service red;
3. a **request field** (`documents`) the bundled server does not accept, and a
   response shape (`{"results": ...}`) it does not return;
4. **413 Payload Too Large** — 50 candidates, some of them whole tables, in one
   request against a server that accepts 32 and 2 MB.

All four were swallowed by `except Exception` in the Rerank step, which degrades
to document diversification. Nothing failed. Answers came back, cited 12 blocks
drawn one per document, and read like a ranking problem.

## With the reranker actually running

| | reranker down (silently) | reranker working |
|---|---|---|
| table | 3/8 (38%) | **4/8 (50%)** |
| text | 2/2 | 2/2 |
| trap (as graded) | 3/7 | 2/7 |

**f5 passes.** That is the case this whole investigation started from: asked for
FLEXI's taux de sélection SR, the assistant used to answer 83,27 %, which is
RHONE-ALPES's. It now answers 44,20 %.

The trap score fell, and the trap score is lying. Read by hand, those answers
improved in exactly the direction the contrast rule asks for:

- f16 now says "7,16 % selon le rapport daté du 30/09/2024. **Cependant, il
  existe une autre valeur pour la même période dans un rapport daté** …" — it
  names the period and admits another exists.
- f12 enumerates each fund with its own value.
- f11 distinguishes the annualised table from the cumulative one.

All three are scored FAIL because the trap grader passes only on refusal. That
is the grading limit recorded in the Makefile, and it is now material: the
metric moved down while the product moved up.

## What changed about the problem

The remaining table failures are no longer retrieval failures. f3's citations
are now 6-of-8 on the right fund, and the answer still takes 0,54 — which is
FLEXI's volatility. f1 takes the "3 ans" column when asked for "5 ans". f6 takes
0,89, FLEXI's sensibilité.

Retrieval now puts the right documents at the top and the model still reaches
for the wrong cell. That is table reading, and it belongs to `make eval-tables`
(88.4 % on the box, the misses recorded as deep-pivot sub-row misattribution)
and to the parser-model question, not to anything in this plan.

## The lesson worth keeping

Every one of the four defects predates this work, and all four were invisible
because the Rerank step catches everything and degrades. "Never fail an answer"
is the right rule and it turned four configuration errors into four silent
years. Degrading quietly is correct for a role nobody configured; a role that IS
configured and whose first call fails should say so once, loudly, and show as
"configured, last call failed" on the Models page.


---

# Final baseline, with the grader fixed

```
contrast: 2/5 = 40%
table   : 4/8 = 50%
text    : 2/2 = 100%   PASS
trap    : 2/2 = 100%   PASS
```

The numbers no longer contradict themselves. `trap` is 2/2 because it now holds
only the two questions where refusal IS the answer — a value absent from the
edition the question pins. `contrast` separates the two behaviours it was built
to separate: f12 and f16 pass because they attribute, f11, f15 and f17 fail
because they state one version and say nothing about the others.

## Where the remaining failures actually live

Not in retrieval. f3's citations are 6-of-8 on the right fund and the answer
still reads:

> "La volatilité annualisée sur 3 ans du portefeuille EPSENS OBLIGATIONS VERTES
> ISR SOLIDAIRE ... est de 0,54 %. Cette information provient du rapport
> **EPSENS FLEXI TAUX COURT ISR SOLIDAIRE**"

It names its source correctly and answers the wrong question anyway. 0,54 is
FLEXI's volatility. f6 does the same with 0,89, FLEXI's sensibilité. f1 takes
the "3 ans" column when asked for "5 ans".

`SYSTEM_PROMPT` already carries the rule this violates — "check the source's
document name and summary really cover what is asked; if none of them do, say
so instead of taking a number from a look-alike table". The model does not obey
it. That is a model-capability question on a 14B chat model, and the same
family as the eval-tables misses README records at 88.4 % ("deep-pivot sub-row
misattribution").

Three levers remain, none of them in this plan:

1. the chat model (this is where f3 and f6 are decided),
2. the parser model (this is where f1 is decided — `make eval-parser` exists to
   answer it on this corpus rather than on someone else's benchmark),
3. the ingestion defect on `EPSENS MONETAIRE ISR - 4004.pdf`, whose reporting
   date never reached the index.


---

# The detection gate, and the number that was missing

`make eval-detection`, 12 pages across the six EPSENS factsheets, graded on
whether a printed value can be reached through ANY accepted table region:

```
pages where every value is reachable: 3/12 = 25%
```

Beside `make eval-tables` at 88.4 %, which grades transcription of tables
already cropped for it. Both are true and only together are they honest:
**reading a table that was found works 88 % of the time; finding it on a real
factsheet works 25 % of the time.**

## The pattern

| result | pages | what they have in common |
|---|---|---|
| PASS | defis-p2, rhone-p2, monetaire-p2 | ONE table, largely alone on the page |
| 0 found | vertes-p2, flexi-p2 | risk indicators AND sensitivity on one page |
| 0 found | climat-p1, climat-p2 | a table beside a chart; two tables side by side |
| 0 found | defis-p1 | three performance tables stacked |
| 3/4, 2/4 | the other p1s | missing exactly LES PRINCIPALES LIGNES |

`PRINCIPALES LIGNES` is found on monetaire-p2, where it stands alone, and missed
on every page 1, where it sits beside the allocation chart. Detection fails when
a table has to share a page: `find_tables` either merges everything into one
page-wide blob — correctly rejected, since accepting it recreates the swallowing
bug — or returns nothing.

## Why this explains the whole day

Three retrieval interventions failed to move `table 4/8`:

1. scope in record text — improved a string retrieval never consulted;
2. the reranker fix — brought the right documents, which held no table;
3. the structured-slot quota — let tables in, but only the ones that exist.

None could have worked. The value 50,46 exists nowhere but page prose, because
the table holding it was never built. A ranking change cannot retrieve a table
that ingestion did not make.

## What this does NOT say

It does not say PyMuPDF is the wrong tool, or that a VLM would do better. It
says the current detection path reaches 25 % on this corpus, and that any
alternative now has a number to beat measured on real customer documents rather
than on a synthetic set.

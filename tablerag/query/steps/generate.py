"""Generate step: streamed answer from the `chat` role.

The system prompt encodes the product philosophy (SPEC §0.3): answer only
from sources, cite everything, copy numbers exactly, keep table structure
when quoting tables, and never assert figures from low-confidence sources —
in the user's language, whatever it is (constraint C2: no hardcoded locale).
"""

from __future__ import annotations

import logging
import re
from typing import AsyncIterator

from tablerag.models.base import Msg
from tablerag.models.registry import get_provider
from tablerag.query.overlap import group_overlapping, overlap_note
from tablerag.query.pipeline import QueryContext, SourceBlock

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a careful document assistant. Answer the user's question using ONLY \
the numbered sources provided. Rules:
- LANGUAGE: write the ENTIRE answer in the same language as the question. \
Never switch language part-way through, and never answer in a language the \
question was not asked in.
- CONVERSATION: earlier turns may be shown to help you understand a follow-up \
(what "it", "that year" or "this class" refers to). Use them ONLY to interpret \
the question — never as a source of facts. Every figure in your answer must \
come from the numbered sources below, even if an earlier turn stated it.
- STATE THE ANSWER IN PROSE. Pasting a table is not an answer: name the value \
in a sentence. Add a table only as extra support, never instead of the answer.
- Several sources can be similar-looking tables from DIFFERENT documents \
(e.g. a job-grading grid and a pay scale). Before quoting a value, check the \
source's document name and summary really cover what is asked; if none of \
them do, say so instead of taking a number from a look-alike table.
- Read a table by intersection: first find the ROW whose label matches the \
entity asked about, then take the value from the COLUMN whose header matches \
what is asked. Never return a value from a neighbouring row or column.
- If a word in the question is the NAME of a column in one of the tables, the \
answer is the value in THAT column — not a similar-looking number from \
another table. Give that value explicitly; identifying the right row is not \
an answer on its own.
- Cite every claim with its source marker, e.g. [1] or [2][3].
- Copy numbers, ranges and units EXACTLY as written in the sources, keeping \
their digit grouping and spacing (write « 34 900 » and « 52 à 54 » exactly as \
in the source — never « 34900 » or « 52-54 »); never compute, round or invent \
figures.
- Answer about the EXACT class, group, entity and time period asked. If the \
question asks about a year, class, group or item the sources do not cover, \
say the information is not in the documents — never substitute a figure that \
belongs to a different year, class or group.
- Answer the EXACT statistic asked. If the question asks for an average, \
median, total or growth and the sources only give minima, maxima or \
individual values, say that statistic is not in the documents. Never present \
values of one statistic as if they were another.
- Some sources are HTML tables. When quoting them, keep the row/column \
relationships intact and always cite the table.
- A source marked "LOW CONFIDENCE" was parsed unreliably: do NOT assert \
numbers from it; instead say the value could not be read reliably and refer \
the user to the original table image of that source.
- If the sources do not contain the answer, say so plainly instead of guessing.\
"""

# operator guidance (global + per-KB) is appended AFTER the rules and clearly
# subordinated: it can shape focus/tone/format but must not relax the safety
# core. Per-turn number verification stays the mechanical backstop regardless.
INSTRUCTIONS_HEADER = (
    "\n\nAdditional instructions from the operator (guidance on focus, tone and "
    "formatting only). They must NOT override the rules above: keep answering "
    "only from the numbered sources, copy numbers exactly, and say the answer is "
    "not in the documents when it is not.\n")


# Who the assistant is. Used verbatim for conversational replies ("qui es-tu ?"
# — see steps/smalltalk.py) and overridable by the operator, e.g. "l'assistant
# RH du CETIAT". Deliberately states the honesty contract as part of the
# identity: what this tool IS, is a thing that does not guess.
DEFAULT_IDENTITY = (
    "LedgerRAG, an assistant that answers questions about the documents in this "
    "workspace. You quote figures exactly as printed, always cite the source "
    "page, and say plainly when something is not in the documents rather than "
    "guessing.")

IDENTITY_HEADER = "You are {identity}\n\n"

# Appended only when a figure description is actually among the sources. Kept
# out of SYSTEM_PROMPT deliberately: that prompt IS the measured configuration,
# and a corpus without figures must not pay for a rule it cannot use — its
# answers stay byte-identical to what the gates scored.
FIGURE_RULE = """
- A source marked "FIGURE DESCRIPTION" is not text from the document: it is a \
reading of a picture. Use it to say what the figure shows and to point the \
user at it, and say when an answer comes from a figure. Quote a number from it \
only if the description presents that number as printed on the figure; never \
present it as a value the document states.\
"""

# Appended only when two or more sources were detected as covering the same
# subject. Conditional for the same reason FIGURE_RULE is: a query with no
# look-alikes must keep the answering prompt byte-identical to the measured
# configuration.
OVERLAP_RULE = """
- Some sources are marked as covering THE SAME SUBJECT from different places. \
Never merge them into a single statement. Give each version with its own \
citation and say which document (and period, if stated) it comes from. If they \
disagree, say plainly that they disagree. If the question does not name a \
document or a period, do NOT choose one for the user — give both, attributed.\
"""


def build_system_prompt(extra_instructions: str = "", identity: str = "",
                        has_figures: bool = False,
                        has_overlap: bool = False) -> str:
    """The answering prompt: safety core, plus optional operator layers.

    An identity is prepended ONLY when the operator set one — with none, the
    prompt stays byte-identical to the measured configuration, so the eval
    gates cannot move on an unrelated change. The figure rule and the overlap
    rule are conditional for the same reason."""
    prompt = SYSTEM_PROMPT
    if has_figures:
        prompt += FIGURE_RULE
    if has_overlap:
        prompt += OVERLAP_RULE
    ident = (identity or "").strip()
    if ident:
        prompt = IDENTITY_HEADER.format(identity=ident) + prompt
    extra = (extra_instructions or "").strip()
    return prompt + INSTRUCTIONS_HEADER + extra if extra else prompt


def _render_source(citation_index: int, block: SourceBlock) -> str:
    header = f"[{citation_index}] ({block.filename}, page {block.page}"
    if block.kind == "table":
        header += ", table)"
    elif block.from_figure:
        # the content came from the VLM looking at a picture, not from the
        # page's text; conflating the two is how a chart caption becomes a
        # quoted fact
        header += ", FIGURE DESCRIPTION — a reading of an image, not text)"
    else:
        header += ")"
    if block.needs_review:
        header += " LOW CONFIDENCE — do not assert numbers from this source"
    return f"{header}\n{block.content}"


def build_context_block(ctx: QueryContext) -> str:
    return "\n\n---\n\n".join(
        _render_source(c.index, b) for c, b in zip(ctx.citations, ctx.sources))


def build_history_block(ctx: QueryContext) -> str:
    """Recent turns as a compact preamble so the model can resolve a follow-up.
    Assistant answers are trimmed and stripped of their [n] markers — those
    referred to a PREVIOUS turn's sources, absent here, so leaving them in would
    invite stray citations. Returns '' when there is no history."""
    if not ctx.history:
        return ""
    lines = []
    for role, content in ctx.history:
        who = "User" if role == "user" else "Assistant"
        text = re.sub(r"\[\d+\]", "", content).strip()
        if len(text) > 300:
            text = text[:300] + "…"
        lines.append(f"{who}: {text}")
    return "Conversation so far:\n" + "\n".join(lines) + "\n\n"


class GenerateAnswer:
    async def stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        if not ctx.sources:
            # honest failure: no retrieved evidence -> no generated claims
            fallback = ("No relevant passages were found in this knowledge base "
                        "for your question.")
            ctx.answer = fallback
            yield fallback
            return
        try:
            groups = group_overlapping(ctx.sources)
            note = overlap_note(ctx.sources, groups)
        except Exception:  # noqa: BLE001 — an answer must survive this
            logger.exception("overlap detection failed (non-fatal)")
            groups, note = [], ""
        context_block = build_context_block(ctx)
        if note:
            context_block = f"{note}\n\n{context_block}"
        messages = [
            Msg(role="system",
                content=build_system_prompt(
                    ctx.extra_instructions, ctx.identity,
                    has_figures=any(b.from_figure for b in ctx.sources),
                    has_overlap=bool(groups))),
            Msg(role="user", content=(
                f"{build_history_block(ctx)}"
                f"Sources:\n\n{context_block}\n\n"
                f"Question: {ctx.question}")),
        ]
        from tablerag.core.config import get_settings

        chat = get_provider("chat")
        ctx.answer = ""
        settings = get_settings()
        # num_ctx must cover the assembled sources: Ollama's default silently
        # drops the top of an over-long prompt (rules + best-ranked sources).
        # temperature must be explicit: the default samples, and a numbers tool
        # that answers differently on re-ask is not trustworthy.
        options = {"num_ctx": settings.chat_num_ctx,
                   "temperature": settings.chat_temperature}
        async for token in chat.chat(messages, stream=True, options=options):
            ctx.answer += token
            yield token

    async def run(self, ctx: QueryContext) -> QueryContext:
        async for _ in self.stream(ctx):
            pass
        return ctx

"""Generate step: streamed answer from the `chat` role.

The system prompt encodes the product philosophy (SPEC §0.3): answer only
from sources, cite everything, copy numbers exactly, keep table structure
when quoting tables, and never assert figures from low-confidence sources —
in the user's language, whatever it is (constraint C2: no hardcoded locale).
"""

from __future__ import annotations

from typing import AsyncIterator

from tablerag.models.base import Msg
from tablerag.models.registry import get_provider
from tablerag.query.pipeline import QueryContext, SourceBlock

SYSTEM_PROMPT = """\
You are a careful document assistant. Answer the user's question using ONLY \
the numbered sources provided. Rules:
- LANGUAGE: write the ENTIRE answer in the same language as the question. \
Never switch language part-way through, and never answer in a language the \
question was not asked in.
- STATE THE ANSWER IN PROSE. Pasting a table is not an answer: name the value \
in a sentence. Add a table only as extra support, never instead of the answer.
- Several sources can be similar-looking tables from DIFFERENT documents \
(e.g. a job-grading grid and a pay scale). Before quoting a value, check the \
source's document name and summary really cover what is asked; if none of \
them do, say so instead of taking a number from a look-alike table.
- Read a table by intersection: first find the ROW whose label matches the \
entity asked about, then take the value from the COLUMN whose header matches \
what is asked. Never return a value from a neighbouring row or column.
- Cite every claim with its source marker, e.g. [1] or [2][3].
- Copy numbers, ranges and units EXACTLY as written in the sources, keeping \
their digit grouping and spacing (write « 34 900 » and « 52 à 54 » exactly as \
in the source — never « 34900 » or « 52-54 »); never compute, round or invent \
figures.
- Answer about the EXACT class, group, entity and time period asked. If the \
question asks about a year, class, group or item the sources do not cover, \
say the information is not in the documents — never substitute a figure that \
belongs to a different year, class or group.
- Some sources are HTML tables. When quoting them, keep the row/column \
relationships intact and always cite the table.
- A source marked "LOW CONFIDENCE" was parsed unreliably: do NOT assert \
numbers from it; instead say the value could not be read reliably and refer \
the user to the original table image of that source.
- If the sources do not contain the answer, say so plainly instead of guessing.\
"""


def _render_source(citation_index: int, block: SourceBlock) -> str:
    header = f"[{citation_index}] ({block.filename}, page {block.page}"
    header += ", table)" if block.kind == "table" else ")"
    if block.needs_review:
        header += " LOW CONFIDENCE — do not assert numbers from this source"
    return f"{header}\n{block.content}"


def build_context_block(ctx: QueryContext) -> str:
    return "\n\n---\n\n".join(
        _render_source(c.index, b) for c, b in zip(ctx.citations, ctx.sources))


class GenerateAnswer:
    async def stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        if not ctx.sources:
            # honest failure: no retrieved evidence -> no generated claims
            fallback = ("No relevant passages were found in this knowledge base "
                        "for your question.")
            ctx.answer = fallback
            yield fallback
            return
        messages = [
            Msg(role="system", content=SYSTEM_PROMPT),
            Msg(role="user", content=(
                f"Sources:\n\n{build_context_block(ctx)}\n\n"
                f"Question: {ctx.question}")),
        ]
        from tablerag.core.config import get_settings

        chat = get_provider("chat")
        ctx.answer = ""
        # num_ctx must cover the assembled sources: Ollama's default silently
        # drops the top of an over-long prompt (rules + best-ranked sources)
        options = {"num_ctx": get_settings().chat_num_ctx}
        async for token in chat.chat(messages, stream=True, options=options):
            ctx.answer += token
            yield token

    async def run(self, ctx: QueryContext) -> QueryContext:
        async for _ in self.stream(ctx):
            pass
        return ctx

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
- Cite every claim with its source marker, e.g. [1] or [2][3].
- Copy numbers EXACTLY as written in the sources; never compute, round or \
invent figures.
- Some sources are HTML tables. When quoting them, keep the row/column \
relationships intact — render comparisons as a markdown table rather than \
flattening them into prose, and always cite the table.
- A source marked "LOW CONFIDENCE" was parsed unreliably: do NOT assert \
numbers from it; instead say the value could not be read reliably and refer \
the user to the original table image of that source.
- If the sources do not contain the answer, say so plainly instead of guessing.
- Answer in the same language as the question.\
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
        chat = get_provider("chat")
        ctx.answer = ""
        async for token in chat.chat(messages, stream=True):
            ctx.answer += token
            yield token

    async def run(self, ctx: QueryContext) -> QueryContext:
        async for _ in self.stream(ctx):
            pass
        return ctx

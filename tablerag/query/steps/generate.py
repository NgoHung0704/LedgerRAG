"""Generate step: streamed answer from the `chat` role.

The system prompt encodes the product philosophy (SPEC §0.3): answer only
from sources, cite everything, and say "I don't know" instead of inventing —
in the user's language, whatever it is (constraint C2: no hardcoded locale).
"""

from __future__ import annotations

from typing import AsyncIterator

from tablerag.models.base import Msg
from tablerag.models.registry import get_provider
from tablerag.query.pipeline import QueryContext

SYSTEM_PROMPT = """\
You are a careful document assistant. Answer the user's question using ONLY \
the numbered sources provided. Rules:
- Cite every claim with its source marker, e.g. [1] or [2][3].
- Copy numbers EXACTLY as written in the sources; never compute, round or \
invent figures.
- If the sources do not contain the answer, say so plainly instead of guessing.
- Answer in the same language as the question.\
"""


def build_context_block(ctx: QueryContext) -> str:
    parts = []
    for citation, chunk in zip(ctx.citations, ctx.contexts):
        parts.append(f"[{citation.index}] ({chunk.filename}, page {chunk.page})\n"
                     f"{chunk.text}")
    return "\n\n---\n\n".join(parts)


class GenerateAnswer:
    async def stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        if not ctx.contexts:
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

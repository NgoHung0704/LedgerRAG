"""Condense step (multi-turn): rewrite a follow-up into a standalone question.

A conversational follow-up — "et pour la classe II ?", "and in 2022 ?" — is a
fragment. Retrieval and routing act on the text alone, so the fragment
retrieves the wrong table (or nothing) and routes to the wrong KB. Before
anything else in the chain, we fold the recent thread into one self-contained
question that downstream steps can search on.

Guardrails, matching the product's honesty rule (SPEC §0.3):
  - runs ONLY when there is prior history — the first turn is a pure
    passthrough, so the measured single-turn gates (eval-qa, eval-routing) are
    byte-identical and cannot regress;
  - any failure, or an empty/oversized reply, falls back to the raw question;
  - it only rewrites the QUESTION. The answer still comes solely from freshly
    retrieved, cited sources (see GenerateAnswer) — history never becomes a fact.
"""

from __future__ import annotations

import logging

from tablerag.query.pipeline import QueryContext

logger = logging.getLogger(__name__)

CONDENSE_SYSTEM = """\
You rewrite a user's latest message into a standalone question for a document \
search. Use the conversation so far only to fill in what the latest message \
leaves implicit (which entity, year, class or table it refers to). Rules:
- Keep the SAME language as the latest message.
- If the latest message is already self-contained, return it unchanged.
- Do not answer, explain or add anything. Output ONLY the rewritten question, \
on one line.\
"""

# each turn is trimmed so the condense prompt stays small and the model focuses
# on intent, not on re-reading long answers
_MAX_TURN_CHARS = 400
# a rewrite longer than this means the model started answering instead of
# condensing — fall back to the raw question rather than search on a paragraph
_MAX_REWRITE_CHARS = 400


def build_condense_prompt(history: list[tuple[str, str]], question: str) -> str:
    lines = []
    for role, content in history:
        who = "User" if role == "user" else "Assistant"
        text = content.strip()
        if len(text) > _MAX_TURN_CHARS:
            text = text[:_MAX_TURN_CHARS] + "…"
        lines.append(f"{who}: {text}")
    return ("Conversation so far:\n" + "\n".join(lines)
            + f"\n\nLatest message: {question}\n\nStandalone question:")


class CondenseQuestion:
    async def run(self, ctx: QueryContext) -> QueryContext:
        ctx.search_question = ctx.question
        if not ctx.history:
            return ctx
        try:
            rewritten = await self._condense(ctx)
        except Exception:  # noqa: BLE001 — condensing must never kill the query
            logger.exception("condense failed; searching on the raw question")
            return ctx
        rewritten = (rewritten or "").strip().strip('"').strip()
        if rewritten and len(rewritten) <= _MAX_REWRITE_CHARS:
            ctx.search_question = rewritten
            logger.info("condensed follow-up -> %r", rewritten)
        return ctx

    async def _condense(self, ctx: QueryContext) -> str:
        from tablerag.models.base import Msg
        from tablerag.models.registry import get_provider

        chat = get_provider("chat")
        messages = [
            Msg(role="system", content=CONDENSE_SYSTEM),
            Msg(role="user",
                content=build_condense_prompt(ctx.history, ctx.question)),
        ]
        parts: list[str] = []
        async for token in chat.chat(messages, stream=True, temperature=0.0,
                                     options={"temperature": 0.0}):
            parts.append(token)
        return "".join(parts)

"""Router step: chooses which KB(s) to query.

KB isolation + routing is the product's founding idea (SPEC §2 design note).
Phase 1 shipped the no-op SingleKBRouter; Phase 5 adds LLMRouter, which reads
the question plus every kb.description and may select several KBs. Everything
downstream already filters by `routed_kb_ids` (the Qdrant search does a
kb_id MatchAny), so the swap is plug-in only — principle #4 paying off.

Routing is the known dead end (SPEC): route to the wrong KB and the answer is
lost even with a perfect pipeline. Two guards, both here:
  - a manual pin (ctx.pinned_kb_ids) always wins, no LLM involved;
  - any router failure — bad JSON, empty pick, model down — degrades to
    searching ALL KBs, never to searching none. Searching too much costs a
    little relevance; searching nothing is a dead end.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass

from tablerag.query.pipeline import QueryContext

logger = logging.getLogger(__name__)

_JSON_ARRAY = re.compile(r"\[[^\[\]]*\]")


class SingleKBRouter:
    async def run(self, ctx: QueryContext) -> QueryContext:
        ctx.routed_kb_ids = [ctx.kb_id]
        ctx.routing = {"mode": "single", "kb_ids": [str(ctx.kb_id)]}
        return ctx


@dataclass
class KBRef:
    id: uuid.UUID
    name: str
    description: str


ROUTER_SYSTEM = """\
You direct a question to the knowledge base(s) that can answer it. You are \
given a numbered list of knowledge bases, each with a short description of \
what it contains. Reply with ONLY a JSON array of the numbers of the \
knowledge bases relevant to the question — e.g. [1] for one, [2,3] for \
several. Choose every base that could plausibly help; if you are unsure, \
include more rather than fewer. Output the JSON array and nothing else.\
"""


def build_router_prompt(question: str, kbs: list[KBRef]) -> str:
    lines = [f"{i + 1}. {kb.name} — {kb.description or '(no description)'}"
             for i, kb in enumerate(kbs)]
    return ("Knowledge bases:\n" + "\n".join(lines)
            + f"\n\nQuestion: {question}\n\nRelevant knowledge bases (JSON array):")


def parse_router_choice(text: str, n: int) -> list[int]:
    """Zero-based indices of the chosen KBs, parsed from the model's reply.

    Tolerant: finds the first JSON array anywhere in the text, keeps only
    in-range 1-based numbers, dedupes preserving order. Returns [] when nothing
    valid is found so the caller can fall back to all KBs."""
    match = _JSON_ARRAY.search(text or "")
    if not match:
        return []
    try:
        raw = json.loads(match.group())
    except json.JSONDecodeError:
        return []
    seen: set[int] = set()
    out: list[int] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            idx = int(item) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < n and idx not in seen:
            seen.add(idx)
            out.append(idx)
    return out


class LLMRouter:
    """Route across KBs with one LLM call. `list_kbs_fn` and the chat provider
    are resolved lazily so the step is trivially testable."""

    def __init__(self, list_kbs_fn=None):
        self._list_kbs_fn = list_kbs_fn

    async def run(self, ctx: QueryContext) -> QueryContext:
        # manual override: the user pinned specific KBs — honor them exactly
        if ctx.pinned_kb_ids:
            ctx.routed_kb_ids = list(ctx.pinned_kb_ids)
            ctx.routing = {"mode": "pinned",
                           "kb_ids": [str(k) for k in ctx.routed_kb_ids]}
            return ctx

        kbs = await self._fetch_kbs()
        all_ids = [kb.id for kb in kbs]
        if len(kbs) <= 1:  # nothing to decide
            ctx.routed_kb_ids = all_ids or [ctx.kb_id]
            ctx.routing = {"mode": "trivial",
                           "kb_ids": [str(k) for k in ctx.routed_kb_ids]}
            return ctx

        try:
            chosen = await self._route(ctx.search_query, kbs)
        except Exception:  # noqa: BLE001 — routing must never kill the query
            logger.exception("LLM routing failed; searching all KBs")
            chosen = []

        if chosen:
            ctx.routed_kb_ids = [kbs[i].id for i in chosen]
            mode = "llm"
        else:
            ctx.routed_kb_ids = all_ids  # degrade to all, never to none
            mode = "fallback_all"
        ctx.routing = {"mode": mode, "candidates": len(kbs),
                       "kb_ids": [str(k) for k in ctx.routed_kb_ids],
                       "names": [kbs[i].name for i in chosen] if chosen else None}
        logger.info("router: %s -> %d/%d KB(s)", mode,
                    len(ctx.routed_kb_ids), len(kbs))
        return ctx

    async def _route(self, question: str, kbs: list[KBRef]) -> list[int]:
        from tablerag.models.base import Msg
        from tablerag.models.registry import get_provider

        chat = get_provider("chat")
        messages = [Msg(role="system", content=ROUTER_SYSTEM),
                    Msg(role="user", content=build_router_prompt(question, kbs))]
        parts: list[str] = []
        async for token in chat.chat(messages, stream=True, temperature=0.0,
                                     options={"temperature": 0.0}):
            parts.append(token)
        return parse_router_choice("".join(parts), len(kbs))

    async def _fetch_kbs(self) -> list[KBRef]:
        if self._list_kbs_fn is not None:
            return await self._list_kbs_fn()
        import asyncio

        from tablerag.storage import repositories as repo
        from tablerag.storage.db import session_scope

        def load() -> list[KBRef]:
            with session_scope() as s:
                return [KBRef(id=kb.id, name=kb.name,
                              description=(kb.description or ""))
                        for kb in repo.list_kbs(s)]

        return await asyncio.to_thread(load)

"""Print the context a question would actually put in front of the model.

Runs the real query pipeline up to (and excluding) generation, so what this
prints is byte-for-byte what the chat model is asked to answer from. Use it
before theorising about a wrong answer: three fixes in a row were aimed at
what the context was ASSUMED to contain rather than what it did contain.

    docker compose exec api python -m tablerag.scripts.debug_context \\
        --kb <kb_id> "Quelle est la cotation du poste Comptable ?"

`--full` prints whole blocks instead of a head, `--prompt` prints the exact
assembled user message.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from tablerag.core.logging import setup_logging
from tablerag.query.pipeline import QueryContext
from tablerag.query.steps.assemble import AssembleContext
from tablerag.query.steps.generate import SYSTEM_PROMPT, build_context_block
from tablerag.query.steps.rerank import Rerank
from tablerag.query.steps.retrieve import Retrieve
from tablerag.query.steps.router import SingleKBRouter

HEAD_CHARS = 700


async def run(kb_id: str, question: str, full: bool, show_prompt: bool) -> None:
    from tablerag.core.config import get_settings
    from tablerag.storage.db import session_scope
    from tablerag.storage import repositories as repo

    settings = get_settings()
    with session_scope() as s:
        kb = repo.get_kb(s, uuid.UUID(kb_id))
        locale = (kb.config or {}).get("locale") if kb else None

    ctx = QueryContext(kb_id=uuid.UUID(kb_id), question=question, locale=locale)
    for step in (SingleKBRouter(),
                 Retrieve(top_k=settings.retrieve_candidates),
                 Rerank(top_k=settings.rerank_top_k,
                        fallback_top_k=settings.retrieve_top_k),
                 AssembleContext()):
        ctx = await step.run(ctx)

    print(f"question: {question}")
    print(f"locale  : {locale}")
    print(f"{len(ctx.hits)} hits -> {len(ctx.sources)} context blocks "
          f"(order below is the order the model reads)\n")
    for citation, block in zip(ctx.citations, ctx.sources):
        flag = " LOW CONFIDENCE" if block.needs_review else ""
        print("=" * 78)
        print(f"[{citation.index}] {block.kind} · {block.filename} · "
              f"page {block.page} · score {block.score:.4f}{flag}")
        print("-" * 78)
        body = block.content
        print(body if full or len(body) <= HEAD_CHARS
              else body[:HEAD_CHARS] + f"\n… (+{len(body) - HEAD_CHARS} chars)")
    if show_prompt:
        print("\n" + "=" * 78)
        print("SYSTEM PROMPT\n" + "-" * 78)
        print(SYSTEM_PROMPT)
        print("=" * 78)
        print("USER MESSAGE\n" + "-" * 78)
        print(f"Sources:\n\n{build_context_block(ctx)}\n\nQuestion: {question}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--full", action="store_true",
                    help="print whole blocks instead of the first lines")
    ap.add_argument("--prompt", action="store_true",
                    help="also print the exact system + user message")
    args = ap.parse_args()
    setup_logging()
    asyncio.run(run(args.kb, args.question, args.full, args.prompt))


if __name__ == "__main__":
    main()

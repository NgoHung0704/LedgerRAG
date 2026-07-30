"""An assistant for correcting a parsed element, inside the editor.

It manipulates content the reviewer already has — restructure this HTML, drop
the empty column, turn these lines into a table — and hands back a full new
version for review. The load-bearing rule is that it may REARRANGE but never
ADD: a rewrite that quietly invents a figure would poison exactly the records
answers quote numbers from, and it would look perfectly plausible.

The reply is prose plus, when it changed something, one fenced block holding the
complete new content. Nothing is applied automatically.
"""

from __future__ import annotations

import re

from tablerag.models.base import Msg
from tablerag.models.registry import get_provider

# what the reviewer is editing; named so the model knows the target syntax
FORMATS = {
    "html": "an HTML table",
    "text": "markdown text",
    "records": "a JSON array of records ({dimensions, metrics, raw_values})",
    "summary": "a one-or-two sentence summary",
}

SYSTEM_PROMPT = """\
You help someone correct one element extracted from a document page. They give \
you its CURRENT content and an instruction.

Rules:
- Work ONLY from the content given. Never invent, complete, translate or alter \
a figure, a name, a date or a word that is not already there. You may \
restructure, reformat, reorder, split, merge and delete; you may NOT add facts.
- If the instruction asks for something the content does not contain, say so \
plainly instead of filling the gap.
- When you change the content, output the COMPLETE new version in ONE fenced \
code block, and leave everything you were not asked to touch exactly as it was.
- If the instruction is a question, just answer it — no code block.
- Answer in the same language as the instruction, and keep it short.\
"""

_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*[ \t]*\n(.*?)```", re.DOTALL)


def split_reply(text: str) -> tuple[str, str | None]:
    """(prose, proposed new content). The proposal is the first fenced block;
    without one the model only answered, and nothing is offered to apply."""
    match = _FENCE.search(text or "")
    if match is None:
        return (text or "").strip(), None
    proposal = match.group(1).strip("\n")
    prose = ((text[:match.start()] + text[match.end():]).strip()
             or "Here is the updated content.")
    return prose, (proposal or None)


def build_user_message(fmt: str, content: str, instruction: str) -> str:
    kind = FORMATS.get(fmt, "content")
    return (f"Current content ({kind}):\n```\n{content}\n```\n\n"
            f"Instruction: {instruction}")


async def assist(fmt: str, content: str, instruction: str,
                 history: list[tuple[str, str]] | None = None
                 ) -> tuple[str, str | None]:
    """Ask the chat model to help edit. Returns (reply, proposal|None)."""
    messages = [Msg(role="system", content=SYSTEM_PROMPT)]
    for role, text in (history or []):
        messages.append(Msg(role=role, content=text))
    messages.append(Msg(role="user",
                        content=build_user_message(fmt, content, instruction)))

    chat = get_provider("chat")
    parts: list[str] = []
    async for token in chat.chat(messages, stream=True, temperature=0.0,
                                 options={"temperature": 0.0}):
        parts.append(token)
    return split_reply("".join(parts))

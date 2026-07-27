"""LedgerRAG MCP server (stdio).

Exposes the knowledge bases to MCP clients — Claude Desktop, Cursor, Claude Code
— by wrapping the LedgerRAG HTTP API. Run it on the machine where the MCP client
lives, pointing LEDGERRAG_API_URL at your API (default http://localhost:8000).

Register it, e.g. in an MCP client config:

    {"mcpServers": {"ledgerrag": {
        "command": "python",
        "args": ["-m", "tablerag.mcp.server"],
        "env": {"LEDGERRAG_API_URL": "http://192.168.5.106:8000"}}}}

Tools:
  - list_knowledge_bases()  — the KBs and their document counts
  - ask(question, kb=None)  — a grounded, cited answer; honest-failure signals
                              (needs-review sources, unverified numbers) kept
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP

from tablerag.mcp.client import (
    KBNotFoundError,
    LedgerRAGClient,
    api_base_url,
    format_answer,
)

mcp = FastMCP("ledgerrag")


def _unreachable(error: Exception) -> str:
    return (f"Could not reach the LedgerRAG API at {api_base_url()} ({error}). "
            "Check LEDGERRAG_API_URL and that the API is running.")


@mcp.tool()
async def list_knowledge_bases() -> str:
    """List the LedgerRAG knowledge bases available to query, with how many
    documents each holds and how many are ready / processing / failed. Use this
    to discover a knowledge base's name before calling `ask` with it."""
    try:
        kbs = await LedgerRAGClient().list_kbs()
    except httpx.HTTPError as e:
        return _unreachable(e)
    if not kbs:
        return "No knowledge bases exist yet."
    lines = []
    for k in kbs:
        counts = f"{k.done}/{k.total} ready"
        if k.failed:
            counts += f", {k.failed} failed"
        if k.processing:
            counts += f", {k.processing} processing"
        desc = f" — {k.description}" if k.description else ""
        lines.append(f"- {k.name} ({counts}){desc}")
    return "\n".join(lines)


@mcp.tool()
async def ask(question: str, kb: str | None = None) -> str:
    """Ask a question and get an answer grounded in the LedgerRAG documents,
    with citations to the source file and page.

    Numbers in the answer are cross-checked against the cited sources: figures
    that could not be matched, and low-confidence (needs-review) sources, are
    flagged rather than hidden — treat those flags as real, do not present a
    flagged number as established fact.

    Args:
        question: The question. Prefer the documents' own language when known.
        kb: Optional knowledge base name (or id) to restrict the search to. Omit
            to let the router pick across all knowledge bases. Call
            `list_knowledge_bases` first if unsure of the name.
    """
    try:
        answer = await LedgerRAGClient().ask(question, kb=kb)
    except KBNotFoundError as e:
        return str(e)
    except httpx.HTTPError as e:
        return _unreachable(e)
    return format_answer(answer)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

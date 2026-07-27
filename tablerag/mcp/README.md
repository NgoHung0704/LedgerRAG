# LedgerRAG MCP server

Exposes your LedgerRAG knowledge bases to MCP clients — **Claude Desktop,
Cursor, Claude Code** — so you can ask grounded, cited questions about your
documents from inside the assistant.

It is a thin **stdio** server that wraps the LedgerRAG HTTP API. Run it on the
machine where the MCP client lives; point `LEDGERRAG_API_URL` at your running
API. It talks only to the API — it does not touch Postgres/Qdrant directly.

## Install

On the machine with the MCP client (not necessarily the server):

```bash
pip install -e ".[mcp]"        # from the repo root
# or, once published:  pip install "tablerag[mcp]"
```

## Configure

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `LEDGERRAG_API_URL` | `http://localhost:8000` | Base URL of your running LedgerRAG API |
| `LEDGERRAG_MCP_TIMEOUT` | `300` | Read timeout (s) — answer generation can be slow on a local LLM |
| `LEDGERRAG_API_USER` | — | Only if the API runs with proxy auth: value sent as `X-Forwarded-User` |

### Claude Desktop  (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "ledgerrag": {
      "command": "python",
      "args": ["-m", "tablerag.mcp.server"],
      "env": { "LEDGERRAG_API_URL": "http://192.168.5.106:8000" }
    }
  }
}
```

### Cursor  (`.cursor/mcp.json`) — same shape

```json
{
  "mcpServers": {
    "ledgerrag": {
      "command": "python",
      "args": ["-m", "tablerag.mcp.server"],
      "env": { "LEDGERRAG_API_URL": "http://192.168.5.106:8000" }
    }
  }
}
```

### Claude Code

```bash
claude mcp add ledgerrag --env LEDGERRAG_API_URL=http://192.168.5.106:8000 \
  -- python -m tablerag.mcp.server
```

(If installed as a console script, use `ledgerrag-mcp` in place of
`python -m tablerag.mcp.server`.)

## Tools

- **`list_knowledge_bases()`** — the KBs and their document counts
  (ready / processing / failed). Call this to learn a KB's name.
- **`ask(question, kb=None)`** — a grounded answer with citations to file + page.
  Omit `kb` to let the router pick across all KBs, or pass a KB name/id to pin
  the search.

### Honest-failure signals are preserved

`ask` deliberately keeps LedgerRAG's safety signals in the reply instead of
laundering them away:

- sources flagged **⚠ needs review** (a table the parser was unsure about);
- **⚠ Unverified numbers** — figures in the answer that could **not** be matched
  against the cited sources.

Treat those as real: a flagged number is not established fact.

## Notes

- The server is unrelated to the API/worker deployment — it runs next to the MCP
  client, so `pip install -e ".[mcp]"` there does not need the full stack.
- All logic except the MCP wiring lives in `client.py` (no `mcp` dependency) and
  is covered by `tests/unit/test_mcp.py`.

"""LedgerRAG MCP integration.

`client.py` holds the HTTP/parsing/formatting logic (no `mcp` dependency, so it
is unit-testable on its own); `server.py` wires those into an MCP stdio server.
"""

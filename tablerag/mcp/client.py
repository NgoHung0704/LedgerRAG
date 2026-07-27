"""HTTP client for the LedgerRAG API, used by the MCP server.

Deliberately free of the `mcp` dependency so the request / SSE-parsing /
answer-formatting logic is unit-testable without the server runtime. It talks to
a *running* LedgerRAG API (LEDGERRAG_API_URL) and never touches Postgres/Qdrant
directly — ingestion↔query↔serving stay behind the API (principle #1).

The MCP surface is intentionally small: list the knowledge bases, and ask a
grounded question. Crucially, `ask` preserves LedgerRAG's honest-failure signals
(needs-review sources, numbers that could not be verified against the sources)
so the calling agent sees them rather than a laundered answer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx


def api_base_url() -> str:
    return os.environ.get("LEDGERRAG_API_URL", "http://localhost:8000").rstrip("/")


def _timeout() -> httpx.Timeout:
    # answer generation on a local LLM can take a while; be generous on read,
    # tight on connect so an unreachable API fails fast.
    read = float(os.environ.get("LEDGERRAG_MCP_TIMEOUT", "300"))
    return httpx.Timeout(read, connect=10.0)


def _auth_headers() -> dict[str, str]:
    # proxy-auth deployments gate the API behind a user header; let the MCP user
    # pass an identity through. Ignored when the API runs with auth disabled.
    user = os.environ.get("LEDGERRAG_API_USER")
    return {"X-Forwarded-User": user} if user else {}


class KBNotFoundError(Exception):
    def __init__(self, query: str, available: list[str]):
        self.query = query
        self.available = available
        super().__init__(
            f"No knowledge base matches {query!r}. "
            f"Available: {', '.join(available) or '(none)'}")


@dataclass
class KBInfo:
    id: str
    name: str
    description: str = ""
    total: int = 0
    done: int = 0
    processing: int = 0
    failed: int = 0


@dataclass
class Citation:
    index: int
    filename: str
    page: int
    snippet: str
    needs_review: bool = False


@dataclass
class Answer:
    text: str = ""
    citations: list[Citation] = field(default_factory=list)
    routing: dict | None = None
    verification: dict | None = None
    error: str | None = None


# ----------------------------------------------------------------- parsing

def parse_sse_frame(frame: str) -> dict | None:
    """The JSON payload of one `data:` SSE frame, or None if the frame carries
    no valid data line (blank separators, comments)."""
    for line in frame.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                return json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                return None
    return None


def _kb_from_json(kb: dict) -> KBInfo:
    status = kb.get("doc_status") or {}
    return KBInfo(
        id=str(kb.get("id", "")), name=kb.get("name", ""),
        description=kb.get("description", "") or "",
        total=status.get("total", 0), done=status.get("done", 0),
        processing=status.get("processing", 0), failed=status.get("failed", 0))


def _citation_from_json(c: dict) -> Citation:
    return Citation(index=c.get("index", 0), filename=c.get("filename", ""),
                    page=c.get("page", 0), snippet=c.get("snippet", "") or "",
                    needs_review=bool(c.get("needs_review")))


def _apply_event(frame: str, tokens: list[str], answer: Answer) -> None:
    event = parse_sse_frame(frame)
    if not event:
        return
    etype = event.get("type")
    if etype == "token":
        tokens.append(event.get("content", ""))
    elif etype == "citations":
        answer.citations = [_citation_from_json(c) for c in event.get("citations", [])]
    elif etype == "done":
        answer.routing = event.get("routing")
        answer.verification = event.get("verification")
    elif etype == "error":
        answer.error = event.get("message", "unknown error")


def assemble_answer(sse_text: str) -> Answer:
    """Fold a full SSE chat response into one Answer (tokens joined, citations /
    routing / verification captured)."""
    answer = Answer()
    tokens: list[str] = []
    for frame in sse_text.split("\n\n"):
        _apply_event(frame, tokens, answer)
    answer.text = "".join(tokens).strip()
    return answer


# ----------------------------------------------------------------- formatting

def format_answer(answer: Answer) -> str:
    """Render an Answer for an MCP client — answer text, cited sources, and the
    honest-failure signals kept visible (needs-review sources, unverified
    numbers), because hiding them would defeat the point of a numbers tool."""
    if answer.error:
        return f"The assistant could not answer: {answer.error}"

    parts = [answer.text or "(no answer returned)"]

    if answer.citations:
        lines = ["", "**Sources:**"]
        for c in answer.citations:
            flag = " ⚠ needs review" if c.needs_review else ""
            snippet = " ".join((c.snippet or "").split())
            if len(snippet) > 160:
                snippet = snippet[:159] + "…"
            suffix = f" — {snippet}" if snippet else ""
            lines.append(f"- [{c.index}] {c.filename} p.{c.page}{flag}{suffix}")
        parts.append("\n".join(lines))

    verification = answer.verification or {}
    if verification.get("status") == "warnings":
        unverified = verification.get("unverified") or []
        if unverified:
            parts.append(
                "\n⚠ **Unverified numbers** (not matched in the cited sources — "
                "do not rely on these): " + ", ".join(str(u) for u in unverified))

    routing = answer.routing or {}
    if routing.get("names"):
        parts.append(f"\n_Searched knowledge base(s): {', '.join(routing['names'])}_")

    return "\n".join(parts)


# ----------------------------------------------------------------- client

class LedgerRAGClient:
    def __init__(self, base_url: str | None = None, *,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or api_base_url()).rstrip("/")
        self._transport = transport  # tests inject an httpx.MockTransport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=_timeout(),
                                 headers=_auth_headers(), transport=self._transport)

    async def list_kbs(self) -> list[KBInfo]:
        async with self._client() as client:
            resp = await client.get("/api/kbs")
            resp.raise_for_status()
            return [_kb_from_json(kb) for kb in resp.json()]

    async def resolve_kb_ids(self, kb: str) -> list[str]:
        """Map a KB name (case-insensitive; exact then substring) or id to its
        id. Raises KBNotFoundError with the available names on no match."""
        kbs = await self.list_kbs()
        for k in kbs:
            if k.id == kb:
                return [k.id]
        exact = [k for k in kbs if k.name.lower() == kb.lower()]
        if exact:
            return [exact[0].id]
        partial = [k for k in kbs if kb.lower() in k.name.lower()]
        if partial:
            return [partial[0].id]
        raise KBNotFoundError(kb, [k.name for k in kbs])

    async def ask(self, question: str, kb: str | None = None) -> Answer:
        """Ask via the multi-KB chat endpoint. When `kb` is given it pins the
        search to that KB; otherwise the server's router picks. The SSE stream is
        collected and folded into a single Answer."""
        kb_ids = await self.resolve_kb_ids(kb) if kb else None
        payload = {"question": question, "kb_ids": kb_ids}
        async with self._client() as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            return assemble_answer(resp.text)

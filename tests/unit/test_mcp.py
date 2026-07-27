"""MCP client logic — SSE folding, KB resolution, honest-failure formatting.

Tests the `mcp` client wrapper against a mocked HTTP API (httpx.MockTransport),
so no `mcp` package and no live server are needed.
"""

import httpx
import pytest

from tablerag.mcp.client import (
    Answer,
    Citation,
    KBNotFoundError,
    LedgerRAGClient,
    assemble_answer,
    format_answer,
    parse_sse_frame,
)

_KBS = [
    {"id": "id-accords", "name": "ACCORDS", "description": "accords d'entreprise",
     "doc_status": {"total": 42, "done": 9, "processing": 0, "failed": 33}},
    {"id": "id-dhr", "name": "DHR", "description": "",
     "doc_status": {"total": 3, "done": 3, "processing": 0, "failed": 0}},
]

_SSE = (
    'data: {"type":"citations","citations":[{"index":1,"filename":"a.pdf",'
    '"page":3,"snippet":"line one\\nline two","needs_review":true}]}\n\n'
    'data: {"type":"token","content":"Hello "}\n\n'
    'data: {"type":"token","content":"world"}\n\n'
    'data: {"type":"done","routing":{"names":["ACCORDS"]},'
    '"verification":{"status":"warnings","unverified":["7 462 639"]}}\n\n'
)


def test_parse_sse_frame():
    assert parse_sse_frame('data: {"type":"token","content":"x"}') == {
        "type": "token", "content": "x"}
    assert parse_sse_frame(": comment only") is None
    assert parse_sse_frame("data: not json") is None


def test_assemble_answer_folds_tokens_and_signals():
    ans = assemble_answer(_SSE)
    assert ans.text == "Hello world"
    assert len(ans.citations) == 1
    assert ans.citations[0].filename == "a.pdf" and ans.citations[0].needs_review
    assert ans.routing == {"names": ["ACCORDS"]}
    assert ans.verification["status"] == "warnings"


def test_assemble_answer_captures_error_event():
    ans = assemble_answer('data: {"type":"error","message":"boom"}\n\n')
    assert ans.error == "boom"


def test_format_answer_surfaces_honest_failure_signals():
    ans = Answer(
        text="La cotisation est de 7 462 639.",
        citations=[Citation(1, "a.pdf", 3, "the source snippet", needs_review=True)],
        routing={"names": ["ACCORDS"]},
        verification={"status": "warnings", "unverified": ["7 462 639"]})
    out = format_answer(ans)
    assert "**Sources:**" in out
    assert "a.pdf p.3" in out and "needs review" in out
    assert "Unverified numbers" in out and "7 462 639" in out
    assert "ACCORDS" in out


def test_format_answer_error():
    assert format_answer(Answer(error="down")).startswith("The assistant could not answer")


async def test_list_kbs():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/kbs"
        return httpx.Response(200, json=_KBS)

    client = LedgerRAGClient("http://test", transport=httpx.MockTransport(handler))
    kbs = await client.list_kbs()
    assert [k.name for k in kbs] == ["ACCORDS", "DHR"]
    assert kbs[0].failed == 33 and kbs[1].done == 3


async def test_ask_without_kb_uses_router_and_folds_stream():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(200, text=_SSE)

    client = LedgerRAGClient("http://test", transport=httpx.MockTransport(handler))
    ans = await client.ask("combien ?")
    assert seen["path"] == "/api/chat"
    assert b'"kb_ids":null' in seen["body"]  # no KB pinned -> router picks
    assert ans.text == "Hello world"
    assert ans.verification["unverified"] == ["7 462 639"]


@pytest.mark.parametrize("query,expected", [
    ("id-dhr", "id-dhr"),      # exact id
    ("dhr", "id-dhr"),         # case-insensitive exact name
    ("accord", "id-accords"),  # substring
])
async def test_resolve_kb_ids(query, expected):
    client = LedgerRAGClient(
        "http://test",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_KBS)))
    assert await client.resolve_kb_ids(query) == [expected]


async def test_resolve_kb_ids_not_found_lists_available():
    client = LedgerRAGClient(
        "http://test",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_KBS)))
    with pytest.raises(KBNotFoundError) as exc:
        await client.resolve_kb_ids("nope")
    assert "ACCORDS" in str(exc.value) and "DHR" in str(exc.value)

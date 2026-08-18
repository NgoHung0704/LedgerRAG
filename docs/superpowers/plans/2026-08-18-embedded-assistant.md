# Embedded Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one assistant be dropped into another internal application as an `<iframe>`, without handing over the rest of the API.

**Architecture:** A token stored on the assistant's config identifies one embed. A dedicated `/api/embed` prefix — the only prefix `auth_middleware` lets through without an identity — exchanges that token for the assistant and runs the existing chat pipeline unchanged. The page it serves is the normal `ChatPanel` with the application shell removed, and it refuses to be framed until someone names the origins allowed to host it.

**Tech Stack:** FastAPI, SQLAlchemy (JSONB config, no migrations), Next.js 14 App Router, React 18, vitest + jsdom, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-embedded-assistant-design.md`

## Global Constraints

- **The token lives in `assistant.config["embed_token"]`.** No new table. Same JSONB idiom as `opening_message`, `verify`, `escalation_contact`. **One token per assistant.**
- **A blank or whitespace token is not a token.** `"   "` must resolve to nothing, everywhere it is read.
- **`/api/embed` is the only new open prefix.** Every route under it validates the token itself. `POST /api/assistants/{id}/chat` is not modified in behaviour — only refactored so both entry points share one implementation.
- **The embed chat route takes no assistant id.** The token is the identity.
- **404, never 403,** for an unknown, blank or revoked token — on every embed route.
- **`frame-ancestors` defaults to `'none'`.** No embed works until origins are configured.
- **The pipeline does not change.** Same `caution_for`, same verification, same escalation contact, same citations. Any task that finds itself editing `tablerag/query/` has gone out of scope — stop and report.
- **Rate limiting is out of scope** (intranet). So is a second embed per assistant.
- Run `python -m pytest tests/unit -q` and `cd frontend && npx tsc --noEmit && npx vitest run` after every task. Run `python docs-site/tools/relink.py --write` when a Python file's line numbers shift, and register any new module in `docs-site/content/components.json`.

---

### Task 1: The token on the assistant

**Files:**
- Modify: `tablerag/core/schemas.py` (AssistantCreate, AssistantUpdate, AssistantOut)
- Modify: `tablerag/api/routes/assistants.py` (`_out`, `create_assistant`, `update_assistant`)
- Modify: `tablerag/storage/repositories.py` (new lookup)
- Test: `tests/unit/test_embed_token.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `repo.get_assistant_by_embed_token(s: Session, token: str) -> Assistant | None`; `AssistantOut.embed_token: str`; `AssistantCreate.embed_token` is NOT added (a token is minted after creation, never supplied by the caller); `AssistantUpdate.embed_token: str | None` where `""` revokes and `"new"` sets.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_embed_token.py`:

```python
"""The token that stands in for one assistant when another application hosts it.

It does not buy secrecy: `auth.mode` is `disabled` on the deployment box, so
everyone who can reach the API on the intranet is already an administrator of
it. It buys revocation, and it buys being able to switch authentication on later
without tearing out a deployed embed.
"""

import uuid

from tablerag.storage import repositories as repo


def _assistant(s, config: dict):
    return repo.create_assistant(s, name="HR", description="", instructions="",
                                 config=config)


def test_a_token_finds_its_assistant(db_session):
    a = _assistant(db_session, {"embed_token": "tok_abc"})
    found = repo.get_assistant_by_embed_token(db_session, "tok_abc")
    assert found is not None and found.id == a.id


def test_an_unknown_token_finds_nothing(db_session):
    _assistant(db_session, {"embed_token": "tok_abc"})
    assert repo.get_assistant_by_embed_token(db_session, "tok_zzz") is None


def test_a_revoked_token_finds_nothing(db_session):
    a = _assistant(db_session, {"embed_token": "tok_abc"})
    a.config = {}
    db_session.flush()
    assert repo.get_assistant_by_embed_token(db_session, "tok_abc") is None


def test_a_blank_token_matches_nothing_even_if_one_is_stored(db_session):
    # the escalation-contact lesson, in the one place where getting it wrong
    # would hand out an assistant to anyone sending an empty string
    _assistant(db_session, {"embed_token": "   "})
    for probe in ("", "   ", "\t"):
        assert repo.get_assistant_by_embed_token(db_session, probe) is None


def test_two_assistants_do_not_collide(db_session):
    a = _assistant(db_session, {"embed_token": "tok_a"})
    b = _assistant(db_session, {"embed_token": "tok_b"})
    assert repo.get_assistant_by_embed_token(db_session, "tok_a").id == a.id
    assert repo.get_assistant_by_embed_token(db_session, "tok_b").id == b.id
    assert uuid.UUID(str(b.id))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_embed_token.py -q`
Expected: FAIL — `AttributeError: module 'tablerag.storage.repositories' has no attribute 'get_assistant_by_embed_token'`.

- [ ] **Step 3: Add the lookup**

In `tablerag/storage/repositories.py`, beside the other assistant helpers:

```python
def get_assistant_by_embed_token(s: Session, token: str) -> Assistant | None:
    """The assistant one embed token stands for, or None.

    Compared in Python rather than in SQL: the token lives inside a JSONB blob,
    and the JSON operators for reaching into it differ between Postgres and the
    SQLite the tests run on. The number of assistants is small enough that this
    is not the query worth optimising.

    A blank token matches nothing, whatever is stored. Without that, an embed
    whose token was cleared to "" would be handed to anyone posting an empty
    string.
    """
    wanted = (token or "").strip()
    if not wanted:
        return None
    for assistant in s.query(Assistant).all():
        if ((assistant.config or {}).get("embed_token") or "").strip() == wanted:
            return assistant
    return None
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/unit/test_embed_token.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Carry the token on the schemas**

In `tablerag/core/schemas.py`, add to `AssistantUpdate`:

```python
    # "" revokes, a value sets. Absent leaves it alone, like every other field
    # here. Not on AssistantCreate: a token is minted from the UI after the
    # assistant exists, never supplied by whoever creates it.
    embed_token: str | None = None
```

and to `AssistantOut`:

```python
    # shown in the deploy panel so the snippet can be copied; empty when no
    # embed has been created
    embed_token: str = ""
```

- [ ] **Step 6: Store and return it**

In `tablerag/api/routes/assistants.py`, in `_out(...)`, beside `escalation_contact=...`:

```python
        embed_token=config.get("embed_token", ""),
```

and in `update_assistant`, beside the `escalation_contact` branch:

```python
        if body.embed_token is not None:
            minted = body.embed_token.strip()
            if minted:
                config["embed_token"] = minted
            else:
                config.pop("embed_token", None)  # revoked
```

- [ ] **Step 7: Verify**

Run: `python -m pytest tests/unit -q`
Expected: all pass. If `test_docs_content.py` fails on line numbers, run `python docs-site/tools/relink.py --write` and re-run.

- [ ] **Step 8: Commit**

```bash
git add tablerag/core/schemas.py tablerag/api/routes/assistants.py \
        tablerag/storage/repositories.py tests/unit/test_embed_token.py \
        docs-site/content
git commit -m "a token that stands for one assistant, and for nothing else"
```

---

### Task 2: The embed routes

**Files:**
- Create: `tablerag/api/routes/embed.py`
- Modify: `tablerag/api/routes/assistants.py` (extract the chat responder)
- Modify: `tablerag/core/auth.py:25` (`OPEN_PREFIXES`)
- Modify: `tablerag/api/main.py` (register the router)
- Modify: `tablerag/core/schemas.py` (`EmbedFace`)
- Test: `tests/unit/test_embed_routes.py`

**Interfaces:**
- Consumes: `repo.get_assistant_by_embed_token` from Task 1.
- Produces: `assistant_chat_response(assistant_id: uuid.UUID, body: AssistantChatRequest, actor: str) -> StreamingResponse` in `routes/assistants.py`; `EmbedFace` with fields `name: str`, `description: str`, `opening_message: str`; routes `GET /api/embed/{token}` and `POST /api/embed/{token}/chat`.

- [ ] **Step 1: Extract the chat responder, changing nothing else**

In `tablerag/api/routes/assistants.py`, rename the body of `assistant_chat` into a plain function and leave the route as a two-line caller:

```python
@router.post("/assistants/{assistant_id}/chat")
async def assistant_chat(assistant_id: uuid.UUID, body: AssistantChatRequest,
                         user: User = Depends(current_user)) -> StreamingResponse:
    """Chat with one assistant: its KBs are the whole search space, its
    instructions shape the answer, and the thread is saved under it. Same SSE
    contract as the other chat endpoints."""
    return await assistant_chat_response(assistant_id, body, user.username)


async def assistant_chat_response(
    assistant_id: uuid.UUID, body: AssistantChatRequest, actor: str,
) -> StreamingResponse:
    """One assistant's chat, whoever is asking.

    Shared by the signed-in route above and the embed route, which differ in
    exactly one thing: who the audit trail records. Duplicating this instead
    would mean two copies of the pipeline wiring, and the embedded one would be
    the copy that quietly stops matching.
    """
    from tablerag.query.steps.router import KBRef, LLMRouter
    ...
```

Move the entire existing body under the new function unchanged, and replace the
two uses of `user.username` inside it — in `repo.log_audit(...)` — with `actor`.

- [ ] **Step 2: Verify the refactor changed no behaviour**

Run: `python -m pytest tests/unit -q`
Expected: unchanged pass count. This step exists because the next one adds a
second caller; a refactor that quietly broke the first would be found much later.

- [ ] **Step 3: Write the failing test**

Create `tests/unit/test_embed_routes.py`:

```python
"""The only prefix the auth middleware lets through without an identity.

That is the risky part of this design, so most of what is tested here is what
the token CANNOT do.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from tablerag.api.main import create_app
from tablerag.core.auth import OPEN_PREFIXES


@pytest.fixture
def client():
    return TestClient(create_app())


def test_the_embed_prefix_is_open_at_the_middleware():
    assert "/api/embed" in OPEN_PREFIXES


def test_every_embed_route_exchanges_a_token():
    """The guard for the door this design opens.

    Adding an endpoint under /api/embed and forgetting to resolve the token
    would publish it to anyone who can reach the port. Enumerated from the app's
    own route table rather than from a list someone maintains by hand.
    """
    app = create_app()
    embed_routes = [r for r in app.routes
                    if getattr(r, "path", "").startswith("/api/embed")]
    assert embed_routes, "no embed routes registered"
    for route in embed_routes:
        assert "{token}" in route.path, (
            f"{route.path} is under the open prefix but takes no token")


def test_an_unknown_token_is_not_found(client):
    assert client.get("/api/embed/nope").status_code == 404


def test_a_blank_token_is_not_found(client):
    assert client.get("/api/embed/%20%20").status_code == 404


def test_the_chat_route_carries_no_assistant_id():
    """A valid token must not be pointable at another assistant."""
    app = create_app()
    chat = [r for r in app.routes
            if getattr(r, "path", "") == "/api/embed/{token}/chat"]
    assert chat, "the embed chat route is not registered at that path"
    assert "assistant_id" not in chat[0].path
```

- [ ] **Step 4: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_embed_routes.py -q`
Expected: FAIL — `/api/embed` is not in `OPEN_PREFIXES` and no embed routes exist.

- [ ] **Step 5: Add the face schema**

In `tablerag/core/schemas.py`, beside `AssistantOut`:

```python
class EmbedFace(BaseModel):
    """What an embedded assistant shows before anyone types.

    Its name, what it is for, and how it opens. Deliberately not AssistantOut:
    that carries the knowledge base ids, the operator instructions and the token
    itself, none of which belongs on a page served to another application.
    """

    name: str
    description: str = ""
    opening_message: str = ""
```

- [ ] **Step 6: Write the router**

Create `tablerag/api/routes/embed.py`:

```python
"""One assistant, served to another application by token.

This is the only prefix `auth_middleware` lets through without an identity, so
every route here resolves the token itself and answers 404 when it does not
match. 404 rather than 403 on purpose: a 403 confirms there is an assistant
there and you merely lack permission.

Nothing else is reachable with a token — not the assistant list, not the
knowledge bases, not upload, not settings. The chat route takes no assistant id,
so a valid token cannot be aimed at a different assistant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from tablerag.api.routes.assistants import assistant_chat_response
from tablerag.core.schemas import AssistantChatRequest, EmbedFace
from tablerag.storage import repositories as repo
from tablerag.storage.db import session_scope

router = APIRouter(prefix="/api/embed", tags=["embed"])


def _resolve(token: str) -> tuple[uuid.UUID, str]:
    """The assistant this token stands for, as (id, name). 404 otherwise."""
    with session_scope() as s:
        assistant = repo.get_assistant_by_embed_token(s, token)
        if assistant is None:
            raise HTTPException(404, "not found")
        return assistant.id, assistant.name


@router.get("/{token}", response_model=EmbedFace)
def embed_face(token: str) -> EmbedFace:
    with session_scope() as s:
        assistant = repo.get_assistant_by_embed_token(s, token)
        if assistant is None:
            raise HTTPException(404, "not found")
        config = assistant.config or {}
        return EmbedFace(name=assistant.name,
                         description=assistant.description or "",
                         opening_message=config.get("opening_message", ""))


@router.post("/{token}/chat")
async def embed_chat(token: str,
                     body: AssistantChatRequest) -> StreamingResponse:
    """The same pipeline the signed-in assistant chat runs.

    The audit actor names the embed rather than a person, because there is no
    person: `embed:<assistant name>` is what /audit will show.
    """
    assistant_id, name = _resolve(token)
    return await assistant_chat_response(assistant_id, body, f"embed:{name}")
```

- [ ] **Step 7: Open the prefix and register the router**

In `tablerag/core/auth.py`:

```python
# open paths: health for load balancers, docs/schema for developers, and the
# embed prefix, whose routes carry their own credential — a token that stands
# for exactly one assistant. Never gate these, or a proxy health check / the
# docs / a deployed embed break.
OPEN_PREFIXES = ("/api/health", "/docs", "/redoc", "/openapi.json", "/api/embed")
```

In `tablerag/api/main.py`, add `embed` to the routes import list and register it
the same way the others are registered.

- [ ] **Step 8: Run it to verify it passes**

Run: `python -m pytest tests/unit/test_embed_routes.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 9: Prove the route guard can fail**

Temporarily add to `tablerag/api/routes/embed.py`:

```python
@router.get("/assistants")
def leak() -> list[str]:
    return ["this endpoint takes no token"]
```

Run: `python -m pytest tests/unit/test_embed_routes.py -q`
Expected: FAIL — `/api/embed/assistants is under the open prefix but takes no token`.
Delete it and re-run. **Do not skip this step:** the whole point of that test is
the door this task opens, and a guard nobody has watched fail is a guard nobody
knows works.

- [ ] **Step 10: Commit**

```bash
git add tablerag/api/routes/embed.py tablerag/api/routes/assistants.py \
        tablerag/core/auth.py tablerag/core/schemas.py tablerag/api/main.py \
        tests/unit/test_embed_routes.py docs-site/content
git commit -m "one prefix a token opens, and nothing else"
```

---

### Task 3: The embedded page

**Files:**
- Create: `frontend/app/embed/[token]/page.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/AppShell.tsx`
- Modify: `frontend/components/ChatPanel.tsx`
- Test: `frontend/components/ChatPanel.embed.test.tsx`

**Interfaces:**
- Consumes: `GET /api/embed/{token}`, `POST /api/embed/{token}/chat` from Task 2.
- Produces: `type EmbedFace = { name: string; description: string; opening_message: string }`; `getEmbedFace(token: string): Promise<EmbedFace>`; `embedChatStream(token: string, question: string, sessionId: string | null): AsyncGenerator<MultiChatEvent>`; `<ChatPanel embedToken={...} />`.

- [ ] **Step 1: Write the failing test**

Create `frontend/components/ChatPanel.embed.test.tsx`:

```tsx
// @vitest-environment jsdom
/**
 * Embedded, ChatPanel talks to the embed endpoint and to nothing else.
 *
 * The token is the credential; posting to /api/assistants/... from an embedded
 * page would 401 the moment authentication is switched on, which is the one
 * thing the token exists to survive.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, fireEvent } from "@testing-library/react";

Element.prototype.scrollIntoView = () => {};

import ChatPanel from "@/components/ChatPanel";
import { LocaleProvider } from "@/components/LocaleProvider";

const calls: string[] = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(String(url));
    return { ok: true, status: 200, body: null, json: async () => ({}) };
  }) as never);
});

describe("an embedded ChatPanel", () => {
  it("asks the embed endpoint, carrying the token", async () => {
    const { container } = render(
      <LocaleProvider locale="fr">
        <ChatPanel embedToken="tok_abc" allKbs={[]} />
      </LocaleProvider>,
    );
    const box = container.querySelector("textarea")!;
    fireEvent.change(box, { target: { value: "quelle volatilité ?" } });
    fireEvent.submit(box.closest("form")!);
    await vi.waitFor(() =>
      expect(calls.some((u) => u.includes("/api/embed/tok_abc/chat"))).toBe(true),
    );
    expect(calls.some((u) => u.includes("/api/assistants/"))).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run components/ChatPanel.embed.test.tsx`
Expected: FAIL — no request reaches `/api/embed/tok_abc/chat`.

- [ ] **Step 3: Add the client calls**

In `frontend/lib/api.ts`, beside `assistantChatStream`:

```ts
/** What an embedded assistant shows before anyone types. */
export type EmbedFace = {
  name: string;
  description: string;
  opening_message: string;
};

export const getEmbedFace = (token: string) =>
  fetch(`${API_URL}/api/embed/${encodeURIComponent(token)}`, {
    cache: "no-store",
  }).then((r) => jsonOrThrow<EmbedFace>(r));

export async function* embedChatStream(
  token: string,
  question: string,
  sessionId: string | null,
): AsyncGenerator<MultiChatEvent> {
  const res = await fetch(
    `${API_URL}/api/embed/${encodeURIComponent(token)}/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId }),
    },
  );
  yield* sseStream<MultiChatEvent>(res);
}
```

- [ ] **Step 4: Add the third branch to ChatPanel**

Add `embedToken?: string;` to the props type, with this comment:

```tsx
  // embedded in another application: the token is the whole credential, so
  // there is no scope picker and no assistant id in any request
  embedToken?: string;
```

In the props destructuring add `embedToken,`. In `showScope`, an embed never
offers a picker — its context is fixed exactly as an assistant's is:

```tsx
  const showScope = assistantId || embedToken
    ? false
    : kbId
      ? allKbs.length > 1
      : allKbs.length >= 1;
```

And in `ask`, the stream selection gains its first branch:

```tsx
    const stream = embedToken
      ? embedChatStream(embedToken, q, sessionRef.current)
      : assistantId
        ? assistantChatStream(assistantId, q, sessionRef.current)
        : scope.mode === "this" && kbId
          ? chatStream(kbId, q, sessionRef.current)
          : chatMultiStream(
              q,
              scope.mode === "pinned" ? Array.from(scope.kbIds) : null,
              sessionRef.current,
            );
```

Import `embedChatStream` alongside the other stream functions.

- [ ] **Step 5: Run it to verify it passes**

Run: `cd frontend && npx vitest run components/ChatPanel.embed.test.tsx`
Expected: PASS.

- [ ] **Step 6: Take the shell off the embed**

In `frontend/components/AppShell.tsx`, immediately after `const pathname = usePathname();`:

```tsx
  // an embedded page is somebody else's page: no rail, no skip link, no chrome
  // of ours around it. The more idiomatic Next answer is two route groups with
  // two layouts, but that means moving every existing page into a new directory
  // for the sake of one exception.
  const embedded = pathname?.startsWith("/embed");
```

and return `children` unwrapped when `embedded` is true, before the existing
return. The `useEffect` above it must stay above that early return — hooks run
unconditionally or React throws on the render where the condition changes.

- [ ] **Step 7: Write the page**

Create `frontend/app/embed/[token]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

import ChatPanel from "@/components/ChatPanel";
import { getEmbedFace, type EmbedFace } from "@/lib/api";

/** One assistant, hosted by another application.
 *
 *  No rail, no navigation, nothing that belongs to this product's own shell —
 *  the host page supplies the frame. What DOES travel is the answer surface:
 *  the caution notice, the verification badge, the inline source chips and the
 *  weighted source list. That is the reason this is an iframe rather than an
 *  API somebody re-renders. */
export default function EmbedPage({ params }: { params: { token: string } }) {
  const [face, setFace] = useState<EmbedFace | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getEmbedFace(params.token).then(setFace).catch(() => setFailed(true));
  }, [params.token]);

  if (failed)
    return (
      <div className="flex h-screen items-center justify-center p-6 text-center text-sm text-ink-muted">
        {/* deliberately says nothing about whether an assistant exists */}
        Not found.
      </div>
    );

  return (
    <div className="flex h-screen flex-col p-3">
      {face && (
        <div className="mb-2 shrink-0">
          <div className="text-sm font-semibold text-ink">{face.name}</div>
          {face.description && (
            <div className="text-xs text-ink-muted">{face.description}</div>
          )}
        </div>
      )}
      <div className="min-h-0 flex-1">
        <ChatPanel embedToken={params.token} allKbs={[]} />
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Read the language off the URL**

The embed has no language picker and its visitor carries no `locale` cookie, so
without this every embed renders in English. In `frontend/app/layout.tsx`, the
locale resolution gains the query string, which the server can read:

```tsx
export default function RootLayout({
  children,
  searchParams,
}: {
  children: React.ReactNode;
  searchParams?: { lang?: string };
}) {
  // the embed is hosted by an application that knows its own user's language
  // and passes it as ?lang=fr; a cookie cannot cross into that first request
  const asked = searchParams?.lang;
  const saved = cookies().get(LOCALE_COOKIE)?.value;
  const locale = isLocale(asked) ? asked : isLocale(saved) ? saved : DEFAULT_LOCALE;
```

If Next does not pass `searchParams` to the root layout on this version, read it
in `app/embed/[token]/page.tsx` with `useSearchParams()` and wrap the panel in a
second `LocaleProvider` with that locale — the provider nests, and the inner one
wins. Verify which applies in Step 9 rather than assuming.

- [ ] **Step 9: Check it end to end**

Run: `cd frontend && npm run dev`, then in another shell mint a token and fetch
the page with a language:

```bash
curl -s -X PATCH http://localhost:8000/api/assistants/<id> \
  -H "Content-Type: application/json" -d '{"embed_token":"tok_demo"}'
curl -s "http://localhost:3000/embed/tok_demo?lang=fr" | grep -o 'lang="[a-z]*"'
curl -s "http://localhost:3000/embed/tok_demo?lang=fr" | grep -c "app-nav"
```

Expected: `lang="fr"`, and `0` occurrences of the navigation rail. If `lang` comes
back `en`, take the fallback described in Step 8.

- [ ] **Step 10: Commit**

```bash
git add frontend/app/embed frontend/lib/api.ts frontend/components/AppShell.tsx \
        frontend/components/ChatPanel.tsx frontend/components/ChatPanel.embed.test.tsx \
        frontend/app/layout.tsx docs-site/content
git commit -m "the embedded page is somebody else's page"
```

---

### Task 4: Framing, and the snippet to paste

**Files:**
- Create: `frontend/middleware.ts`
- Modify: `frontend/components/AssistantForm.tsx`
- Modify: `frontend/messages/{en,fr,vi,es,de}.ts`
- Modify: `.env.example`, `docker-compose.yml`, `README.md`
- Test: `tests/unit/test_embed_framing.py`

**Interfaces:**
- Consumes: `AssistantOut.embed_token` from Task 1, the page from Task 3.
- Produces: the `EMBED_FRAME_ANCESTORS` environment variable, read at request time.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_embed_framing.py`:

```python
"""Nothing may frame the embed until somebody names who may.

A default that works is a default nobody revisits. This one does not work: it
renders frame-ancestors 'none', so a deployment has to state the origins out
loud, and that statement has a person behind it.
"""

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIDDLEWARE = REPO_ROOT / "frontend" / "middleware.ts"


def test_the_embed_carries_a_frame_ancestors_header():
    source = MIDDLEWARE.read_text(encoding="utf-8")
    assert "frame-ancestors" in source
    assert "/embed" in source, "the header must be scoped to the embed path"


def test_the_default_forbids_framing():
    source = MIDDLEWARE.read_text(encoding="utf-8")
    assert "'none'" in source, (
        "with no origins configured the header must render 'none' — an embed "
        "that frames anywhere by default is a decision nobody made")


def test_the_deployment_files_do_not_ship_an_open_default():
    for rel in (".env.example", "docker-compose.yml"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "EMBED_FRAME_ANCESTORS" in line and not line.strip().startswith("#"):
                value = line.split("=", 1)[-1].strip().strip('"\'')
                assert value in ("", "${EMBED_FRAME_ANCESTORS:-}"), (
                    f"{rel} ships a framing default: {line.strip()}")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_embed_framing.py -q`
Expected: FAIL — `frontend/middleware.ts` does not exist.

- [ ] **Step 3: Write the middleware**

Create `frontend/middleware.ts`:

```ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Who may put the embed in an iframe.
 *
 *  Read per request rather than at build time, so a deployment can change it by
 *  restarting the container instead of rebuilding the image.
 *
 *  The default is 'none'. An embed that frames anywhere until someone thinks to
 *  close it is a decision nobody made; this way opening it is one line in the
 *  environment, with a person behind it. */
export function middleware(request: NextRequest) {
  const response = NextResponse.next();
  const origins = (process.env.EMBED_FRAME_ANCESTORS ?? "").trim();
  response.headers.set(
    "Content-Security-Policy",
    `frame-ancestors ${origins || "'none'"}`,
  );
  return response;
}

export const config = { matcher: "/embed/:path*" };
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/unit/test_embed_framing.py -q`
Expected: the first two pass; the third passes only after Step 5.

- [ ] **Step 5: Document the variable without opening it**

In `.env.example`:

```bash
# Origins allowed to put an embedded assistant in an iframe, space separated —
# e.g. "https://intranet.example.com". EMPTY MEANS NOBODY, which is the default
# on purpose: an embed that frames anywhere is a decision nobody made.
EMBED_FRAME_ANCESTORS=
```

In `docker-compose.yml`, pass it through to the `frontend` service:

```yaml
      - EMBED_FRAME_ANCESTORS=${EMBED_FRAME_ANCESTORS:-}
```

In `README.md`, one paragraph beside the other deployment notes: what an embed
is, that the token is minted per assistant in its settings, that revoking is
instant, and that `EMBED_FRAME_ANCESTORS` must name the host origins before any
embed renders.

- [ ] **Step 6: Add the deploy panel**

In `frontend/components/AssistantForm.tsx`, after the escalation-contact block,
a section that shows the snippet when a token exists and a button to mint one
when it does not. Add `const [token, setToken] = useState(assistant?.embed_token ?? "");`
beside the other state, send `embed_token: token` in the submit payload, and
render:

```tsx
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">
            {t("asst.embed")}
          </label>
          {token ? (
            <>
              <textarea
                readOnly
                rows={3}
                className={`${inputCls} font-mono text-[11px]`}
                value={`<iframe src="${typeof window === "undefined" ? "" : window.location.origin}/embed/${token}?lang=fr" width="420" height="600" style="border:1px solid #e5e7eb;border-radius:12px"></iframe>`}
              />
              <div className="mt-1 flex items-center gap-2">
                <Button type="button" size="xs" variant="ghost"
                        onClick={() => setToken(crypto.randomUUID().replace(/-/g, ""))}>
                  {t("asst.embed_regenerate")}
                </Button>
                <Button type="button" size="xs" variant="ghost"
                        onClick={() => setToken("")}>
                  {t("asst.embed_revoke")}
                </Button>
              </div>
              <p className="mt-1 text-xs text-ink-subtle">
                {t("asst.embed_hint")}
              </p>
            </>
          ) : (
            <Button type="button" size="xs" variant="tonal"
                    onClick={() => setToken(crypto.randomUUID().replace(/-/g, ""))}>
              {t("asst.embed_create")}
            </Button>
          )}
        </div>
```

- [ ] **Step 7: Add the five translations**

In `frontend/messages/en.ts` and each of the four others, in the same order
`en, fr, vi, es, de`:

```ts
"asst.embed": "Embed in another application" | "Intégrer dans une autre application" | "Nhúng vào ứng dụng khác" | "Insertar en otra aplicación" | "In eine andere Anwendung einbetten"
"asst.embed_create": "Create an embed" | "Créer une intégration" | "Tạo bản nhúng" | "Crear una inserción" | "Einbettung erstellen"
"asst.embed_regenerate": "Regenerate" | "Régénérer" | "Cấp lại" | "Regenerar" | "Neu erzeugen"
"asst.embed_revoke": "Revoke" | "Révoquer" | "Thu hồi" | "Revocar" | "Widerrufen"
"asst.embed_hint": "Saving a new token stops the running embed immediately. The host origins must also be listed in EMBED_FRAME_ANCESTORS, or the frame stays blank." | "Enregistrer un nouveau jeton coupe immédiatement l'intégration en cours. Les domaines hôtes doivent aussi figurer dans EMBED_FRAME_ANCESTORS, sinon le cadre reste vide." | "Lưu token mới sẽ ngắt bản nhúng đang chạy ngay lập tức. Miền của trang chủ nhà cũng phải có trong EMBED_FRAME_ANCESTORS, nếu không khung sẽ trống." | "Guardar un nuevo token corta la inserción en curso de inmediato. Los dominios anfitriones también deben figurar en EMBED_FRAME_ANCESTORS, o el marco queda vacío." | "Ein neues Token beendet die laufende Einbettung sofort. Die Host-Domains müssen außerdem in EMBED_FRAME_ANCESTORS stehen, sonst bleibt der Rahmen leer."
```

Write each as a normal catalogue entry; `tsc` fails until all five exist.

- [ ] **Step 8: Verify everything**

Run: `python -m pytest tests/unit -q`
Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run build`
Expected: all clean. The guard from Task 1 of the language work — no reader-facing
screen hardcodes copy — covers `AssistantForm.tsx`, so an untranslated string
here turns it red.

- [ ] **Step 9: Check the header is actually sent**

Run: `cd frontend && npm run dev`, then:

```bash
curl -sI "http://localhost:3000/embed/tok_demo" | grep -i content-security-policy
EMBED_FRAME_ANCESTORS="https://intranet.example.com" npm run dev
curl -sI "http://localhost:3000/embed/tok_demo" | grep -i content-security-policy
```

Expected: `frame-ancestors 'none'` first, then `frame-ancestors https://intranet.example.com`.

- [ ] **Step 10: Commit**

```bash
git add frontend/middleware.ts frontend/components/AssistantForm.tsx \
        frontend/messages .env.example docker-compose.yml README.md \
        tests/unit/test_embed_framing.py
git commit -m "nothing frames the embed until somebody says who may"
```

---

## Self-review notes

Checked against the spec section by section:

- *Token in `assistant.config["embed_token"]`, one per assistant, blank is not a
  token* — Task 1, with the blank case tested against three shapes of empty.
- *`GET /api/embed/{token}` and `POST /api/embed/{token}/chat`* — Task 2 Step 6.
- *`OPEN_PREFIXES` gains `/api/embed`, every route under it validates* — Task 2
  Steps 7 and 3, **proven by Step 9**, which requires watching the guard fail.
- *`/api/assistants/{id}/chat` untouched in behaviour* — Task 2 Step 1 extracts a
  shared responder; Step 2 verifies the existing suite before a second caller
  exists.
- *The embed chat route takes no assistant id* — Task 2 Step 3, pinned.
- *404 never 403* — Task 2 Step 6, and tested for unknown and blank tokens.
- *Audit actor `embed:<name>`* — Task 2 Step 6.
- *Chrome-less page* — Task 3 Steps 6–7, checked against the served HTML in Step 9.
- *`?lang=`* — Task 3 Step 8, with a stated fallback rather than an assumption,
  resolved by the check in Step 9.
- *`frame-ancestors` closed by default* — Task 4, including a test that the
  shipped `.env.example` and compose file do not quietly open it.
- *Pipeline unchanged* — no task edits `tablerag/query/`; the Global Constraints
  say to stop and report if one starts to.
- *Out of scope: rate limiting, multiple embeds, switching `auth.mode`* — no task
  touches any of them.

One thing worth flagging to whoever executes this: Task 3 Step 8 is the only
step whose implementation depends on behaviour I did not verify — whether this
Next version passes `searchParams` to a root layout. The step says so and gives
the fallback, and Step 9 is the check that decides. Everything else in this plan
is written against code that was read.

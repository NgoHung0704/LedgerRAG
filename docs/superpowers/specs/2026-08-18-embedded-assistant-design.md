# Embedding an assistant in another application

Design agreed 2026-08-18. One assistant becomes an `<iframe>` another internal
application can drop into its own page. The pipeline behind it does not change.

## The problem

Sharing a knowledge base across applications is already built and needs nothing:
`assistant_kb` is a many-to-many join, so one knowledge base attaches to any
number of assistants, each with its own prompt, persona and escalation contact.
That is the same shape as a Dify dataset shared between apps.

What is missing is the other half. `POST /api/assistants/{id}/chat` exists and
streams, but authentication reads an identity header injected by a reverse proxy
(`core/auth.py`), and a browser loading an iframe on another origin cannot
produce that header. There is no way to hand out one assistant without handing
over the whole admin API.

## The ground truth this is designed on

Measured on the deployment box rather than assumed: `LEDGERRAG_AUTH__MODE` is
unset, so `auth.mode` is **`disabled`** — every request resolves to an implicit
admin. `cors_origins` defaults to `["*"]`. **Everyone who can reach the API on
the intranet is already an administrator of it.**

That changes what the token is for. It does not buy secrecy today; anyone on the
network can call the API directly. It buys two other things:

- **revocation** — turning off one embed without touching anything else;
- **a path to closing the door** — the day `auth.mode` becomes `proxy`, the
  embed keeps working. Given the API is open now, being able to tighten it
  without tearing out a deployed integration is worth the field.

## Decisions taken

| | decision | ruled out |
|---|---|---|
| 1 | **Intranet only.** The embedding app sits on the company network. | Public internet, which would make rate limiting mandatory and raise "who may read the HR corpus" before any technical question. |
| 2 | **An `<iframe>`, not an API integration.** | The other app rebuilding the chat UI. Every honesty signal built into this product — the caution notice, the verification badge, the inline source chips, the weighted bibliography, the see-also row — lives in that UI. An API integration rebuilds them or, more likely, drops the hardest and least-demanded one first: the caution. |
| 3 | **A per-assistant embed token.** | No token at all, which works today but cannot revoke one embed and breaks the moment auth is switched on. |
| 4 | **No rate limiting.** | Deliberate, per decision 1. Becomes mandatory if an embed ever faces the internet. |

## The token

Stored in `assistant.config["embed_token"]`, beside `opening_message`, `verify`
and `escalation_contact` — the same JSONB idiom, and no new table. One token per
assistant. Revoking clears the field; regenerating replaces it and kills the
running embed immediately, which the UI says in words.

A blank or whitespace value is not a token. That is not hypothetical: the
escalation-contact helper shipped the same day promising in its docstring that a
blank was not a contact while `"   " or None` returned three spaces, and a test
calling the real function caught it.

## The surface it opens

```
GET  /api/embed/{token}        the assistant's public face: name, description,
                               opening message
POST /api/embed/{token}/chat   the same pipeline the assistant chat uses
```

`OPEN_PREFIXES` gains `/api/embed`, so `auth_middleware` lets these through
without an identity, and each route exchanges the token for an assistant itself.
`/api/assistants/{id}/chat` is not touched.

The shape matters more than it looks. The alternative — letting a token resolve
to a restricted `User` — would mean every route in the application has to be
re-read to check whether it accidentally accepts that user, and the one that
gets missed is the one nobody remembers. Here, "what can this token do" is
answered by reading one file.

**The embed chat route takes no assistant id.** The token is the identity, so a
valid token cannot be pointed at another assistant.

**404, never 403.** A 403 confirms an assistant exists and you merely lack
permission. A 404 says nothing.

## The page

`app/embed/[token]/page.tsx` fetches the assistant's face and renders
`ChatPanel` with a new `embedToken` prop — a third branch beside the existing
`assistantId` and scoped/multi-KB ones.

`AppShell` returns its children unwrapped when the path starts with `/embed`; it
already reads `usePathname()`. The more idiomatic Next answer is two route
groups with two layouts, but that requires moving every existing page into a new
directory, which is not worth it for one exception.

**Framing is closed by default.** `Content-Security-Policy: frame-ancestors …`
is set in `next.config.js` for `/embed` only, from a configuration value that
defaults to empty — which renders `'none'`, so no embed works until somebody
names the origins allowed to host it. Opening it is a decision with a signature
on it.

**Language comes from the URL.** The embed has no navigation rail and therefore
no language picker, and a first-time visitor from another application carries no
`locale` cookie — so every embed would render in English, which for the actual
customer is wrong. `/embed/{token}?lang=fr` sets the locale for that render,
read on the server from the query rather than a cookie, so the first paint is
still correct.

## What travels with it

The pipeline is unchanged: the same `caution_for`, the same number
verification, the same escalation contact, the same inline source chips. That is
the whole reason decision 2 chose an iframe.

Embedded turns are audited with actor `embed:<assistant name>`, so `/audit`
distinguishes a question asked from another application from one asked here.

## Testing

The negative cases are the ones worth writing:

| case | expected |
|---|---|
| unknown token | 404 on both routes |
| revoked token | 404 |
| whitespace-only token in config | not a token |
| the embed chat route | carries no assistant id — pinned, not assumed |
| `frame-ancestors` unset | `'none'` |

And the guard for the riskiest part of this design, which is adding a prefix to
`OPEN_PREFIXES` — a door opened at the middleware. A test enumerates every route
the application registers under `/api/embed` and asserts each one goes through
the token exchange. Adding an endpoint there and forgetting the check turns the
suite red instead of waiting to be noticed.

Frontend: the embed page renders without the navigation rail, and `ChatPanel`
calls the embed endpoint rather than the assistant one.

## Out of scope

- **Rate limiting.** Intranet, per decision 1. The trigger to revisit is stated
  rather than left implicit: an embed reachable from the internet.
- **Multiple embeds per assistant.** One token, one embed. A second one is when
  the field becomes a table, not before.
- **Turning `auth.mode` on.** A separate decision with its own consequences,
  which this design is built to survive rather than to force.
- **Restyling the embedded chat from the host page.** The host chooses the size
  and the language; the rest is the product's own interface, which is what makes
  the honesty signals travel.

"""How a stored image is served.

The crop is the authority a reviewer reads the parse against (principle #3),
and its URL never changes while its CONTENT does: splitting a table rewrites
the first part's crop in place, and so do joining, undo and reprocessing.

Served with no cache headers, a browser reuses the old picture heuristically.
A table cut in two went on showing the uncut image — the parse had changed and
the evidence beside it had not, which is the one thing that image exists to
prevent.
"""

from __future__ import annotations

import hashlib

from fastapi.responses import Response


def etag_for(content: bytes) -> str:
    return f'"{hashlib.sha1(content).hexdigest()}"'


def stored_image(content: bytes, if_none_match: str | None) -> Response:
    """A PNG that may be replaced at the same URL.

    `no-cache` is not "do not cache": it is "always ask". The ETag makes asking
    free — an unchanged image comes back as a 304 with no body, so revalidating
    every crop on a 40-element page costs a round trip and no pixels."""
    etag = etag_for(content)
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=content, media_type="image/png", headers=headers)

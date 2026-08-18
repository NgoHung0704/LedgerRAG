"""The deployment files must not quietly open the embed.

The header itself is tested where it can be executed rather than read —
`frontend/middleware.test.ts` calls the middleware and checks what it sets. An
earlier version of this file looked for the string "'none'" in the source, which
also appears in the comment above the code, so changing the default to "*" left
it green.

What is left here is the half that is genuinely about file contents: a correct
middleware and a compose file shipping EMBED_FRAME_ANCESTORS=* is an open embed,
and nothing in the frontend would say so.
"""

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_the_deployment_files_do_not_ship_an_open_default():
    seen = 0
    for rel in (".env.example", "docker-compose.yml"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "EMBED_FRAME_ANCESTORS" not in line or line.strip().startswith("#"):
                continue
            seen += 1
            value = line.split("=", 1)[-1].strip().strip('"\'')
            assert value in ("", "${EMBED_FRAME_ANCESTORS:-}"), (
                f"{rel} ships a framing default: {line.strip()}")
    assert seen == 2, (
        f"expected the variable in both deployment files, found {seen} — a "
        f"rename would otherwise make this test pass by matching nothing")

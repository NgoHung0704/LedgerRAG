"""Guards for the interface-language layer.

The frontend has its own unit tests now (`make frontend-test`), but two things
about this feature are not reachable from a TypeScript test: what a Server
Component is allowed to import, and whether any screen still carries copy in a
language nobody chose. Both are read here as text, the way the docs guards read
`.tsx` files.
"""

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _reads_use_client(path: pathlib.Path) -> bool:
    return path.read_text(encoding="utf-8").lstrip().startswith(('"use client"',
                                                                 "'use client'"))


def test_the_cookie_name_does_not_come_from_a_client_module():
    """A Server Component importing a value from a "use client" file gets a
    client REFERENCE, not the value.

    Measured, not theorised. With `LOCALE_COOKIE` exported from
    LocaleProvider.tsx, the layout's `cookies().get(LOCALE_COOKIE)` returned
    undefined while the request carried `[{"name":"locale","value":"fr"}]`, so
    every visitor was served the default language and nothing anywhere said
    why. Switching the picker still worked in-session, which is what makes this
    the kind of defect a look at the screen does not catch: it only shows on
    reload.
    """
    layout = REPO_ROOT / "frontend" / "app" / "layout.tsx"
    source = layout.read_text(encoding="utf-8")
    assert not _reads_use_client(layout), \
        "layout.tsx became a client component; this guard no longer applies"

    imports = re.findall(r'import\s*\{([^}]*)\}\s*from\s*"([^"]+)";', source)
    sources = [spec for names, spec in imports if "LOCALE_COOKIE" in names]
    assert sources, "layout.tsx no longer imports LOCALE_COOKIE — did the " \
                    "cookie read move? Point this guard at wherever it went."

    for spec in sources:
        # both extensions, so a failure here reports the real fault — that the
        # module is a client one — rather than a resolution miss
        base = REPO_ROOT / "frontend" / spec.replace("@/", "")
        module = next((base.with_suffix(ext) for ext in (".ts", ".tsx")
                       if base.with_suffix(ext).exists()), None)
        assert module is not None, f"cannot resolve the import {spec}"
        assert not _reads_use_client(module), (
            f"layout.tsx takes LOCALE_COOKIE from {spec}, which is a client "
            f"module — the server will receive a client reference and read no "
            f"cookie at all")

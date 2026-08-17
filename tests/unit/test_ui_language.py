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


# the reader-facing screens, per the design. Operator screens are out of scope
# and stay English.
TRANSLATED = [
    "frontend/components/Sidebar.tsx",
    "frontend/components/AppShell.tsx",
    "frontend/components/ChatPanel.tsx",
    "frontend/components/ChatScopeSelector.tsx",
    "frontend/components/SourceModal.tsx",
    "frontend/components/CopyButton.tsx",
    "frontend/app/ask/page.tsx",
    "frontend/app/page.tsx",
    "frontend/app/kb/[id]/page.tsx",
]

_LITERAL_WITH_ACCENT = re.compile(
    r"""(["'])([^"'\n]*[àâäéèêëîïôöùûüçñßÀÂÄÉÈÊËÎÏÔÖÙÛÜÇÑ][^"'\n]*)\1""")


def test_no_translated_screen_carries_a_literal_in_another_language():
    """No screen on the reader's path may speak a language nobody chose.

    The app used to be English with about fifteen French strings around the
    answer — I wrote those, reasoning that the reader is a CETIAT employee. The
    reasoning was right about the reader and wrong about the result: the app
    spoke two languages at once and no user had picked either.

    Accented characters are the test, which catches French, Spanish and German
    but NOT an unaccented French sentence ("Vous pouvez consulter le document").
    A tripwire for the common case, not a proof. The proof is that every string
    in these files goes through t().
    """
    offenders = {}
    for rel in TRANSLATED:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        hits = [m.group(2) for m in
                _LITERAL_WITH_ACCENT.finditer(path.read_text(encoding="utf-8"))]
        if hits:
            offenders[rel] = hits[:3]
    assert not offenders, (
        f"reader-facing screens still carry hardcoded copy: {offenders} — "
        f"move it into frontend/messages/ and call t()")


# --- every reader-visible string goes through t() ---------------------------

from tests.unit.ui_text_scan import visible_text  # noqa: E402

# Screens the interface language applies to. The document inspector, the
# element editor and the boilerplate panel are NOT here: they were not part of
# what was asked for, and their copy is dense with rowspan / records / grid
# vocabulary that reads worse translated than left alone.
UI_FILES = sorted(
    [p for p in pathlib.Path("frontend/components").glob("*.tsx")
     if p.name not in {"ElementEditor.tsx", "BoilerplatePanel.tsx",
                       "RecordsTable.tsx"}]
    + [p for p in pathlib.Path("frontend/app").rglob("page.tsx")
       if "doc" not in p.parts])

# Strings that are deliberately not translated, each for a stated reason.
ALLOWED = {
    # a product name is a name
    "LedgerRAG",
    # the project's motto, not interface copy
    "parse it right, or fail honestly",
    # locale CODES and an example URL: data shown as data, the same reason the
    # language picker never translates "Deutsch"
    "fr · de · en · es · (blank = auto)",
    "http://localhost:11434",
}


def test_no_reader_facing_screen_hardcodes_its_own_copy():
    """Everything a reader can read comes from the catalogues.

    This replaces an accent-only check, which could only catch copy I had
    written in French and said nothing about the English that was never
    translated at all. It also sees JSX text nodes spanning several lines,
    which the sweep behind an earlier "no hardcoded strings left" claim could
    not — that is how the whole lede of /ask shipped in English while the app
    around it spoke French.
    """
    offenders = {}
    for path in UI_FILES:
        stray = [s for s in visible_text(path) if s not in ALLOWED]
        if stray:
            offenders[str(path)] = stray[:5]
    assert not offenders, (
        "reader-facing screens still hardcode copy — move it into "
        f"frontend/messages/ and call t():\n{offenders}")

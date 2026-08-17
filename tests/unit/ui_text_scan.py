"""Find user-visible text in a .tsx file, including the kind a grep misses.

A JSX text node wraps across lines and carries no quotes:

    <p className="mt-1 max-w-2xl text-sm text-ink-muted">
      Ask across your knowledge bases. The assistant auto-routes to the
      relevant one(s) by their descriptions — or use{" "}

The sweep behind an earlier "no hardcoded strings left" claim looked for quoted
strings and single-line >Text<. It could not see the paragraph above and
reported the file clean, so the whole lede of /ask, four explanations in the
source modal and "Skip to content" all shipped untranslated.

Everything that can produce a false `>text<` is removed first: comments, arrow
functions, comparison operators, and generic type arguments — `useState<KB[] |
null>(null)` otherwise reads as the text "(null); const [x] = useState".
"""

from __future__ import annotations

import pathlib
import re

_ATTR = re.compile(
    r'\b(?:title|aria-label|placeholder|label|subtitle|alt|hint)="([^"]{3,})"')
_TEXT_NODE = re.compile(r">([^<>{}]*[A-Za-zÀ-ÿ]{3,}[^<>{}]*)<", re.S)
# what survives stripping but is still code, not copy. The property access is
# there for `best > 0 && c.score < best * WEAK_RATIO`, which strips down to the
# innocuous-looking "0 c.score" — no brackets left to give it away.
_CODEISH = re.compile(
    r"[(){};=]|\b\w+\.\w+|^\s*(?:return|const|let|if|else)\b")


def strip_code(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"\{/\*.*?\*/\}", " ", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", " ", src, flags=re.M)
    src = src.replace("=>", " ")
    src = re.sub(r">=|<=|!==|===|&&|\|\|", " ", src)
    for _ in range(3):
        src = re.sub(r"\b([A-Za-z_$][\w$.]*)<([^<>]{0,120})>", r"\1 ", src)
    return src


def visible_text(path: pathlib.Path) -> list[str]:
    """Every string this file would show a reader, best effort."""
    src = strip_code(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for m in _TEXT_NODE.finditer(src):
        text = " ".join(m.group(1).split())
        if not text or _CODEISH.search(text):
            continue
        if re.search(r"[A-Za-zÀ-ÿ]{3,}", text):
            out.append(text)
    out += [m.group(1) for m in _ATTR.finditer(src)]
    return out

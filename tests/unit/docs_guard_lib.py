"""Shared plumbing for the docs-site drift guards.

Kept apart from the test module so the guards read as assertions rather than
as file handling, and so `docs-site/tools/relink.py` can reuse the exact same
line arithmetic the guards use — a relink that disagreed with the guard would
be worse than no relink at all.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT = REPO_ROOT / "docs-site" / "content"

# G3 reads ONLY these. A module named anywhere else in content/ — phases.json
# for instance — must not count as documented: a ticket mentioning a file is
# not somebody writing about it.
COMPONENT_FILES = ("components.json",)
COMPONENT_DIR = "components"


def norm(text: str) -> str:
    """CRLF -> LF. Windows checks out .py/.tsx as CRLF and .md as LF while git
    stores LF, so raw comparison is green on Windows and red on the runner."""
    return text.replace("\r\n", "\n")


def load(name: str) -> Any:
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def load_all() -> dict[str, Any]:
    """Every content file, keyed by its path relative to content/."""
    out: dict[str, Any] = {}
    for path in sorted(CONTENT.rglob("*.json")):
        key = path.relative_to(CONTENT).as_posix()
        out[key] = json.loads(path.read_text(encoding="utf-8"))
    return out


def load_components() -> dict[str, Any]:
    """The component files, and nothing else — see COMPONENT_FILES."""
    out: dict[str, Any] = {}
    for name in COMPONENT_FILES:
        out[name] = load(name)
    for path in sorted((CONTENT / COMPONENT_DIR).glob("*.json")):
        out[f"{COMPONENT_DIR}/{path.name}"] = json.loads(
            path.read_text(encoding="utf-8"))
    return out


def walk(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every node in a JSON tree with a dotted path, parents before children."""
    yield path, obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from walk(value, f"{path}[{i}]")


def citations(files: dict[str, Any]) -> Iterator[tuple[str, dict]]:
    """Every citation object, wherever it sits."""
    for path, node in walk(files):
        if isinstance(node, dict) and node.get("kind") in ("excerpt", "anchor"):
            yield path, node


def file_lines(rel: str) -> list[str]:
    """Normalized lines of a repo file, without their line terminators."""
    return norm((REPO_ROOT / rel).read_text(encoding="utf-8")).split("\n")


def slice_text(rel: str, start: int, end: int) -> str:
    """Lines [start..end], 1-indexed and inclusive, joined with \\n."""
    return "\n".join(file_lines(rel)[start - 1:end])


def source_endpoints() -> set[tuple[str, str]]:
    """(METHOD, full path) for every FastAPI route in the API package.

    The full path is the APIRouter prefix plus the decorator path: the nine
    route modules use five different prefixes, so reading the decorator alone
    would document paths that do not exist.
    """
    found: set[tuple[str, str]] = set()
    routes = REPO_ROOT / "tablerag" / "api" / "routes"
    for path in sorted(routes.glob("*.py")):
        tree = ast.parse(norm(path.read_text(encoding="utf-8")))
        prefix = ""
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "APIRouter"):
                for kw in node.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        prefix = kw.value.value
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if (isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Attribute)
                        and deco.func.attr in
                        ("get", "post", "put", "patch", "delete")
                        and deco.args
                        and isinstance(deco.args[0], ast.Constant)):
                    found.add((deco.func.attr.upper(),
                               prefix + deco.args[0].value))
    return found

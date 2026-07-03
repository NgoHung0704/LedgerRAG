"""Principle #1: ingestion and query pipelines only meet in the storage layer.

Phase 1 DoD: `ingestion/` and `query/` must not import each other — checked
statically over the AST so it cannot be bypassed by lazy imports inside
functions either.
"""

import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[2] / "tablerag"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def assert_no_imports(package: str, forbidden_prefix: str) -> None:
    for file in (PKG_ROOT / package).rglob("*.py"):
        for module in imported_modules(file):
            assert not module.startswith(forbidden_prefix), (
                f"{file.relative_to(PKG_ROOT.parent)} imports {module} — "
                f"pipelines must communicate through storage only (principle #1)")


def test_ingestion_does_not_import_query():
    assert_no_imports("ingestion", "tablerag.query")


def test_query_does_not_import_ingestion():
    assert_no_imports("query", "tablerag.ingestion")


def test_api_does_not_import_ingestion():
    # the API enqueues jobs by task name; importing worker code would drag
    # ingestion dependencies into the gateway process
    assert_no_imports("api", "tablerag.ingestion")

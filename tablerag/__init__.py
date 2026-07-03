"""LedgerRAG — self-hosted multilingual document RAG platform.

Architecture contract (SPEC §2): `ingestion/` (write) and `query/` (read)
never import each other; they communicate only through `storage/` and share
`models/` and `core/`. Enforced by tests/unit/test_architecture.py.
"""

__version__ = "0.1.0"

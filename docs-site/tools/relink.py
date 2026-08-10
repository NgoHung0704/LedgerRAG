"""Repair citation line numbers that merely drifted.

The guards demand that an excerpt match its line range verbatim and that an
anchor sit inside its range. Both break when somebody inserts a line above —
which is not an error, just arithmetic. This repairs exactly that case.

It refuses the case that matters: when the cited TEXT itself changed, the
prose explaining it may now be wrong, and a human has to look. Silently
rewriting the page then would defeat the whole point of the guards.

Anchors are relinked by narrowing the range to the anchor's own span. A
narrower range is a stricter guard, so this never weakens a citation.

    python docs-site/tools/relink.py          # report only
    python docs-site/tools/relink.py --write  # rewrite the JSON in place
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.unit.docs_guard_lib import (  # noqa: E402
    CONTENT,
    file_lines,
    norm,
    slice_text,
)


def find_block(lines: list[str], block: list[str]) -> list[int]:
    """1-indexed start lines where `block` appears contiguously."""
    hits = []
    for i in range(len(lines) - len(block) + 1):
        if lines[i:i + len(block)] == block:
            hits.append(i + 1)
    return hits


def relink_excerpt(cite: dict) -> tuple[bool, str]:
    want = norm(cite["code"]).split("\n")
    if slice_text(cite["file"], cite["from"], cite["to"]) == norm(cite["code"]):
        return False, "ok"
    hits = find_block(file_lines(cite["file"]), want)
    if len(hits) != 1:
        return False, (
            f"REFUSED {cite['file']}:{cite['from']}-{cite['to']} — the code "
            f"itself changed ({len(hits)} matches). A human has to check "
            f"whether the text around it is still true.")
    cite["from"], cite["to"] = hits[0], hits[0] + len(want) - 1
    return True, f"moved to {cite['from']}-{cite['to']}"


def relink_anchor(cite: dict) -> tuple[bool, str]:
    anchor = norm(cite["anchor"])
    if anchor in slice_text(cite["file"], cite["from"], cite["to"]):
        return False, "ok"
    want = anchor.split("\n")
    lines = file_lines(cite["file"])
    hits = [i + 1 for i, line in enumerate(lines) if want[0] in line
            and anchor in "\n".join(lines[i:i + len(want)])]
    if len(hits) != 1:
        return False, (
            f"REFUSED {cite['file']}:{cite['from']}-{cite['to']} — anchor "
            f"{anchor[:40]!r} has {len(hits)} matches. Extend the anchor, or "
            f"check whether what it cited still exists.")
    cite["from"], cite["to"] = hits[0], hits[0] + len(want) - 1
    return True, f"narrowed to {cite['from']}-{cite['to']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    changed_files, refused = 0, 0
    for path in sorted(CONTENT.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        touched = False

        def visit(node):
            nonlocal touched, refused
            if isinstance(node, dict):
                if node.get("kind") == "excerpt":
                    moved, msg = relink_excerpt(node)
                elif node.get("kind") == "anchor":
                    moved, msg = relink_anchor(node)
                else:
                    moved, msg = False, "ok"
                if moved:
                    touched = True
                    print(f"{path.name}: {msg}")
                elif msg.startswith("REFUSED"):
                    refused += 1
                    print(msg)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(data)
        if touched and args.write:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            changed_files += 1

    print(f"\nrewritten: {changed_files} file(s); refused: {refused}")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())

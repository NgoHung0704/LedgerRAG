"""The docs site may not lie about the code.

Every reader-visible claim in docs-site/content/ carries a citation into a
real file, and these guards fail when the two drift apart. They live in
tests/unit because that is the gate the repo already runs (`make test-unit`)
— the site's own toolchain is not required to hold the site honest.
"""

import re

from tests.unit.docs_guard_lib import (
    CONTENT,
    REPO_ROOT,
    citations,
    load,
    load_all,
    norm,
    slice_text,
    source_endpoints,
    source_stores,
    walk,
)

VN_LETTERS = re.compile(
    "[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    "úùủũụứừửữựýỳỷỹỵÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢ"
    "ÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
)

VERBATIM_FIELDS = {"anchor", "code", "decl", "file"}

MIN_ANCHOR = 12


def test_every_content_file_parses():
    files = load_all()
    assert files, f"no content found under {CONTENT}"


def test_localized_strings_have_both_languages():
    for path, node in walk(load_all()):
        if not isinstance(node, dict):
            continue
        if "vi" not in node and "en" not in node:
            continue
        for lang in ("vi", "en"):
            value = node.get(lang)
            assert isinstance(value, str) and value.strip(), (
                f"{path}: localized string is missing a non-empty '{lang}' — "
                f"got {node!r}"
            )


def test_english_strings_are_not_untranslated_vietnamese():
    for path, node in walk(load_all()):
        if not isinstance(node, dict) or "en" not in node:
            continue
        hit = VN_LETTERS.search(node["en"])
        assert not hit, (
            f"{path}.en still carries Vietnamese text ({hit.group(0)!r}) — "
            f"{node['en'][:80]!r}"
        )


def test_every_declared_path_exists():
    for path, node in walk(load_all()):
        if not isinstance(node, dict) or "file" not in node:
            continue
        target = REPO_ROOT / node["file"]
        assert target.is_file(), (
            f"{path} points at {node['file']}, which does not exist"
        )


def test_embedded_code_matches_the_file_verbatim():
    for path, cite in citations(load_all()):
        if cite["kind"] != "excerpt":
            continue
        actual = slice_text(cite["file"], cite["from"], cite["to"])
        assert actual == norm(cite["code"]), (
            f"{path}: the excerpt no longer matches "
            f"{cite['file']}:{cite['from']}-{cite['to']}.\n"
            f"--- content says ---\n{norm(cite['code'])}\n"
            f"--- file says ---\n{actual}\n"
            f"If only the line numbers drifted, run `make docs-relink`."
        )


def test_anchors_sit_inside_their_declared_range():
    for path, cite in citations(load_all()):
        if cite["kind"] != "anchor":
            continue
        anchor = norm(cite["anchor"])
        assert len(anchor) >= MIN_ANCHOR, (
            f"{path}: anchor {anchor!r} is too short to mean anything; "
            f"an anchor must be at least {MIN_ANCHOR} characters"
        )
        whole = norm((REPO_ROOT / cite["file"]).read_text(encoding="utf-8"))
        assert whole.count(anchor) == 1, (
            f"{path}: anchor {anchor!r} occurs {whole.count(anchor)} times in "
            f"{cite['file']} — extend it until it is unique, otherwise "
            f"nothing can tell which occurrence was meant"
        )
        window = slice_text(cite["file"], cite["from"], cite["to"])
        assert anchor in window, (
            f"{path}: anchor {anchor!r} is not inside "
            f"{cite['file']}:{cite['from']}-{cite['to']} any more — the range "
            f"has drifted onto other content. Run `make docs-relink`."
        )


def content_endpoints() -> set[tuple[str, str]]:
    return {(op["method"].upper(), op["path"])
            for edge in load("edges.json")["edges"]
            for op in edge.get("operations", [])}


def test_documented_endpoints_exist_in_the_code():
    missing = sorted(content_endpoints() - source_endpoints())
    assert not missing, (
        "edges.json documents endpoints that no route declares: "
        + ", ".join(f"{m} {p}" for m, p in missing))


def test_every_endpoint_in_the_code_is_documented():
    undocumented = sorted(source_endpoints() - content_endpoints())
    assert not undocumented, (
        "these endpoints exist but no edge documents them — a new endpoint "
        "without a contract is exactly the rot this page exists to prevent: "
        + ", ".join(f"{m} {p}" for m, p in undocumented))


def test_every_store_says_who_writes_it():
    rows = {(r["store"], r["name"]) for r in load("ownership.json")["rows"]}
    missing = sorted(source_stores() - rows)
    assert not missing, (
        "no ownership row for: "
        + ", ".join(f"{s}:{n}" for s, n in missing)
        + " — a new store with no stated writer is the single thing new "
          "developers get wrong most often")
    invented = sorted(rows - source_stores())
    assert not invented, (
        "ownership rows for stores that do not exist: "
        + ", ".join(f"{s}:{n}" for s, n in invented))

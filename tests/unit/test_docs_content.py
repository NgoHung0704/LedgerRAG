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
    load_all,
    norm,
    slice_text,
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

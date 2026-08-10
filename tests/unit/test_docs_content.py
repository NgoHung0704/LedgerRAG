"""The docs site may not lie about the code.

Every reader-visible claim in docs-site/content/ carries a citation into a
real file, and these guards fail when the two drift apart. They live in
tests/unit because that is the gate the repo already runs (`make test-unit`)
— the site's own toolchain is not required to hold the site honest.
"""

import re

from tests.unit.docs_guard_lib import CONTENT, REPO_ROOT, load_all, walk

VN_LETTERS = re.compile(
    "[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    "úùủũụứừửữựýỳỷỹỵÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢ"
    "ÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
)

VERBATIM_FIELDS = {"anchor", "code", "decl", "file"}


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

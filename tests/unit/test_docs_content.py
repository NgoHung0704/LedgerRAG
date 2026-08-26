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
    file_lines,
    load,
    load_all,
    load_components,
    norm,
    slice_text,
    source_endpoints,
    source_modules,
    source_stores,
    walk,
)

VN_LETTERS = re.compile(
    "[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    "úùủũụứừửữựýỳỷỹỵÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢ"
    "ÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
)

VERBATIM_FIELDS = {"anchor", "code", "decl", "file"}

# The languages the page is written in. Adding one here is what forces every
# content file to carry it — a language half-added is worse than none, because
# the reader who picked it gets a page that silently falls back.
LANGS = ("vi", "en", "fr")

MIN_ANCHOR = 12


def test_every_content_file_parses():
    files = load_all()
    assert files, f"no content found under {CONTENT}"


def test_localized_strings_have_every_language():
    for path, node in walk(load_all()):
        if not isinstance(node, dict):
            continue
        if not any(lang in node for lang in LANGS):
            continue
        for lang in LANGS:
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


def documented_modules() -> set[str]:
    """Modules named by a COMPONENT file — nothing else counts.

    Deliberately not `load_all()`: if a module merely appearing in
    phases.json counted, a file a ticket happens to mention would pass as
    documented while nobody had written a line about it.
    """
    out: set[str] = set()
    for name, data in load_components().items():
        for component in data.get("components", []):
            out.update(component.get("modules", []))
    return out


def test_every_source_module_appears_in_a_component():
    missing = sorted(source_modules() - documented_modules())
    assert not missing, (
        f"{len(missing)} module(s) belong to no component — add a new file "
        f"without writing about it and this is what goes red:\n  "
        + "\n  ".join(missing))


def test_components_do_not_claim_modules_that_do_not_exist():
    invented = sorted(documented_modules() - source_modules())
    assert not invented, "components claim non-existent modules:\n  " + \
        "\n  ".join(invented)


def test_component_ids_are_unique():
    ids = [c["id"] for c in load("components.json")["components"]]
    assert len(ids) == len(set(ids)),         f"duplicate component id(s): {sorted({i for i in ids if ids.count(i) > 1})}"


def test_every_phase_reference_resolves():
    phases = {p["id"] for p in load("phases.json")["phases"]}
    for component in load("components.json")["components"]:
        for rel in component["phases"]:
            assert rel["id"] in phases, (
                f"component {component['id']} references unknown phase "
                f"{rel['id']}")
            assert rel["relation"] in ("creates", "modifies", "traverses"), (
                f"component {component['id']} uses unknown relation "
                f"{rel['relation']!r}")


def test_every_phase_is_owned_by_something():
    """The reverse direction. `traverses` does not count: a phase whose only
    tie to the code is 'the request passes through here' owns nothing, and
    would vanish from the diagram the moment anyone filtered by it."""
    owned = {rel["id"]
             for component in load("components.json")["components"]
             for rel in component["phases"]
             if rel["relation"] in ("creates", "modifies")}
    orphans = sorted({p["id"] for p in load("phases.json")["phases"]} - owned)
    assert not orphans, (
        f"phase(s) {orphans} are created or modified by no component — "
        f"filtering by them would light up nothing")


def test_ownership_rows_name_real_components():
    ids = {c["id"] for c in load("components.json")["components"]}
    for row in load("ownership.json")["rows"]:
        for who in [row["owner"], *row["writers"], *row["readers"]]:
            assert who in ids, (
                f"ownership row {row['store']}:{row['name']} names unknown "
                f"component {who!r}")


def test_edges_connect_declared_nodes_and_every_node_is_connected():
    ids = {n["id"] for n in load("nodes.json")["nodes"]}
    touched: set[str] = set()
    for edge in load("edges.json")["edges"]:
        for end in ("from", "to"):
            assert edge[end] in ids,                 f"edge {edge['id']} points at unknown node {edge[end]!r}"
            touched.add(edge[end])
    stranded = sorted(ids - touched)
    assert not stranded, (
        f"node(s) {stranded} are on the map but no edge reaches them — "
        f"either wire them up or take them off")


def test_every_component_has_exactly_one_detail_file():
    listed = {c["id"] for c in load("components.json")["components"]}
    detail = {name.split("/")[1][:-5]
              for name in load_components() if name.startswith("components/")}
    assert listed == detail, (
        f"components without a detail file: {sorted(listed - detail)}; "
        f"detail files with no component: {sorted(detail - listed)}")


def test_detail_file_id_matches_its_filename():
    for name, data in load_components().items():
        if not name.startswith("components/"):
            continue
        assert data["id"] == name.split("/")[1][:-5],             f"{name} declares id {data['id']!r}"


def test_function_declarations_sit_on_the_line_they_claim():
    for name, data in load_components().items():
        for fn in data.get("functions", []):
            whole = norm((REPO_ROOT / fn["file"]).read_text(encoding="utf-8"))
            assert whole.count(fn["decl"]) == 1, (
                f"{name}: {fn['decl']!r} occurs {whole.count(fn['decl'])} "
                f"times in {fn['file']} — extend it until it is unique")
            line = file_lines(fn["file"])[fn["line"] - 1]
            assert fn["decl"] in line, (
                f"{name}: {fn['file']}:{fn['line']} is {line.strip()!r}, "
                f"not {fn['decl']!r}. Run `make docs-relink`.")
            assert fn["name"] in fn["decl"],                 f"{name}: function name {fn['name']!r} is not in its declaration"


def test_flow_diagrams_are_internally_connected():
    for name, data in load_components().items():
        flow = data.get("flow")
        if not flow:
            continue
        ids = ({n["id"] for n in flow["nodes"]}
               | {g["id"] for g in flow.get("gates", [])}
               | {x["id"] for x in flow.get("exits", [])})
        for edge in flow["edges"]:
            for end in ("from", "to"):
                assert edge[end] in ids,                     f"{name}: flow edge points at unknown step {edge[end]!r}"


def test_machine_parts_name_real_components_and_phases():
    components = {c["id"] for c in load("components.json")["components"]}
    phases = {p["id"] for p in load("phases.json")["phases"]}
    for machine in load("machines.json")["machines"]:
        part_ids = {p["id"] for p in machine["parts"]}
        exit_ids = {x["id"] for x in machine["exits"]}
        for part in machine["parts"]:
            assert part["component"] in components, (
                f"machine {machine['id']}: part {part['id']} names unknown "
                f"component {part['component']!r}")
            for phase in part["phases"]:
                assert phase in phases, (
                    f"machine {machine['id']}: part {part['id']} names "
                    f"unknown phase {phase!r}")
        for edge in machine["edges"]:
            for end in ("from", "to"):
                assert edge[end] in part_ids | exit_ids, (
                    f"machine {machine['id']}: edge points at unknown "
                    f"part/exit {edge[end]!r}")


def test_every_machine_part_is_reachable_from_the_inlet():
    """A part nothing feeds is a drawing mistake, not a pipeline."""
    for machine in load("machines.json")["machines"]:
        parts = [p["id"] for p in machine["parts"]]
        reached = {parts[0]}
        for _ in parts:
            for edge in machine["edges"]:
                if edge["from"] in reached:
                    reached.add(edge["to"])
        unreachable = sorted(set(parts) - reached)
        assert not unreachable, (
            f"machine {machine['id']}: {unreachable} cannot be reached from "
            f"the inlet")


SITE_SRC = REPO_ROOT / "docs-site" / "src"
ATTR_LITERAL = re.compile(r'\b(aria-label|title|alt|placeholder)\s*=\s*"')
JSX_TEXT = re.compile(r">\s*([^<>{}\n]*[A-Za-zÀ-ỹ][^<>{}]*)<")


def test_no_reader_visible_string_lives_in_the_site_code():
    """Content is in JSON so guards can check it in the repo's own language.
    A label that slips into a .tsx escapes every check in this file."""
    problems = []
    for path in sorted(SITE_SRC.rglob("*.tsx")):
        text = norm(path.read_text(encoding="utf-8"))
        for i, line in enumerate(text.split("\n"), start=1):
            if ATTR_LITERAL.search(line):
                problems.append(
                    f"{path.name}:{i} literal attribute: {line.strip()}")
            for hit in JSX_TEXT.finditer(line):
                problems.append(
                    f"{path.name}:{i} literal text: {hit.group(1).strip()!r}")
    assert not problems, (
        "these strings must come from docs-site/content/:\n  "
        + "\n  ".join(problems))


# A number written into prose is a claim like any other, but it carries no
# citation, so nothing above catches it when it goes stale. This one did: the
# page said 63 endpoints while the code had 66, through several commits that
# the other guards passed cleanly.
ENDPOINT_COUNT = re.compile(
    r"\b(\d+)\s+(?:endpoints?|points de terminaison)\b")


def test_prose_endpoint_counts_match_the_code():
    real = len(source_endpoints())
    wrong = []
    for path, node in walk(load_all()):
        if not isinstance(node, dict):
            continue
        for lang in LANGS:
            text = node.get(lang)
            if not isinstance(text, str):
                continue
            for hit in ENDPOINT_COUNT.finditer(text):
                if int(hit.group(1)) != real:
                    wrong.append(f"{path}.{lang} says {hit.group(0)!r}")
    assert not wrong, (
        f"the code declares {real} endpoints, but the page says otherwise:\n  "
        + "\n  ".join(wrong)
        + "\n(a count written in prose carries no citation, so only this "
          "guard can keep it honest)")


def test_every_operation_carries_a_citation():
    """A documented endpoint with no pointer into the code is the drift this
    page exists to prevent. Four of them reached the site before this guard
    existed, and the contract panel crashed on the first one it tried to link."""
    naked = [f"{op['method']} {op['path']} (on {edge['id']})"
             for edge in load("edges.json")["edges"]
             for op in edge.get("operations", [])
             if not isinstance(op.get("cite"), dict)]
    assert not naked, "these operations cite nothing:\n  " + "\n  ".join(naked)

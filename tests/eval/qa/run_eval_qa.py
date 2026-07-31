"""`make eval-qa` — the answer-quality gate (SPEC Phase 4 §5).

Feeds real questions through the LIVE query pipeline (API SSE endpoint) and
grades three things per question type:

- table/text: every `expected_answer_contains` string appears in the answer
  AND `expected_doc` is among the citations (right answer FROM the right
  source).
- trap: the system must NOT confidently invent — pass when the number
  verification reports warnings, or no citations were used, or the answer
  contains a refusal marker. Trap grading is heuristic: review failures by
  hand before blaming the pipeline.

Questions file: JSONL, one per line (see questions.example.jsonl). Build it
from real user questions (SPEC: eval data is an asset, feed it from dogfood
logs). DoD: number questions >= 95% correct; traps 100% non-invented.

    python tests/eval/qa/run_eval_qa.py --kb <kb_id> \
        [--api http://localhost:8000] [--questions tests/eval/qa/questions.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import httpx

# Honest "it is not in the documents" detection.
#
# Literal phrase lists are a losing game here: run 2 scored three correct
# refusals as failures because the model wrote "ne contienNENT" (not a
# superstring of "ne contient"), "aucune RÉFÉRENCE" (only "aucune information"
# was listed) and refused in Chinese. So match negation FAMILIES by regex —
# a negator plus any verb/noun of "containing / mentioning / stating" —
# instead of enumerating surface forms. Applied to the normalized answer
# (accent- and apostrophe-folded, see _norm).
#
# "exist" is deliberately NOT in this list. Run 3 scored a fully correct answer
# as a refusal because it wrote "la condition de ressources n'existe pas" —
# an assertion about the WORLD (there is no such condition), not about the
# documents. It gets its own patterns below, which require an
# information-noun and so keep "il n'existe pas d'information".
_VERBS = (r"contien\w*|mentionn\w*|figur\w*|precis\w*|indiqu\w*|fourni\w*"
          r"|comport\w*|permet\w*|dispos\w*|present\w*|apparai\w*"
          r"|trouv\w*|donn\w*|abord\w*|evoqu\w*|specifi\w*")
_NOUNS = (r"information\w*|mention\w*|reference\w*|donnee\w*|indication\w*"
          r"|precision\w*|element\w*|detail\w*")
REFUSAL_PATTERNS = [
    # French: "ne contiennent pas", "n indiquent pas", "ne sont pas precises"
    re.compile(rf"\bne?\s+(?:se\s+|sont\s+|est\s+|peu\w+\s+|pas\s+)*(?:{_VERBS})"),
    # "aucune reference", "aucun element", "sans mention"
    re.compile(rf"\baucun\w*\s+(?:autre\s+)?(?:{_NOUNS})"),
    re.compile(rf"\bsans\s+(?:{_NOUNS})"),
    # "il n'existe pas d'information", "aucune donnée n'existe" — the noun is
    # what makes it a statement about the sources rather than about the subject
    re.compile(rf"\bexist\w*\s+(?:pas\s+)?(?:aucun\w*\s+|d\s+|de\s+|dans\s+)*"
               rf"(?:{_NOUNS})"),
    re.compile(rf"\b(?:{_NOUNS})\s+n\s+exist\w*"),
    # "pas de donnees", "pas d information", "n est pas disponible"
    re.compile(rf"\bpas\s+d\s*(?:{_NOUNS})"),
    re.compile(r"\bpas\s+(?:disponible|mentionne\w*|precise\w*|indique\w*"
               r"|present\w*|connu\w*)"),
    re.compile(r"\bimpossible\s+de\b|\bje\s+ne\s+(?:peux|sais|trouve)\b"),
    # English
    re.compile(r"\b(?:do|does|did)\s+not\s+(?:contain|mention|state|specify"
               r"|include|provide)\b"),
    re.compile(r"\bnot\s+(?:found|available|mentioned|specified|in\s+the\s+"
               r"(?:document|source))\b|\bno\s+(?:information|relevant|data|"
               r"mention)\b|\bcannot\s+(?:answer|determine|be\s+determined)\b"),
    # Vietnamese
    re.compile(r"khong\s+(?:tim\s+thay|co|de\s+cap|nhac|ton\s+tai|xac\s+dinh|"
               r"duoc\s+neu|thay)"),
    # Chinese (the chat model drifts to it — run 2 refused p7 entirely in zh)
    re.compile(r"无法|没有(?:提供|给出|包含|明确)|未(?:提供|给出|直接给出|说明|包含)"
               r"|不能确定|未能找到"),
]


def refusal_marker(normalized: str) -> str | None:
    """The words that made this look like a refusal, or None.

    A refusal veto that only says "refuses/hedges" is not diagnosable: the
    printed answer is truncated, and the trigger is usually in the part that
    was cut. Reporting the match turns a calibration guess into a reading."""
    for p in REFUSAL_PATTERNS:
        m = p.search(normalized)
        if m:
            return m.group(0)
    return None


def is_refusal(normalized: str) -> bool:
    return refusal_marker(normalized) is not None


# Markdown/HTML table rows dumped into an answer are NOT a claim: run 2 had
# answers that stated the wrong cell in prose ("Comptable -> classe 2") or
# refused outright, while pasting a grid that happened to contain the expected
# string. Grading must read what the answer SAYS, not what it pastes.
_MD_ROW = re.compile(r"^\s*\|.*$", re.MULTILINE)
_HTML_TAG = re.compile(r"<[^>]+>")
_PARENS = re.compile(r"\([^)]*\)")


def prose_only(answer: str) -> str:
    """The answer minus dumped table rows — the part that actually asserts."""
    return _HTML_TAG.sub(" ", _MD_ROW.sub(" ", answer))


def without_asides(answer: str) -> str:
    """The answer with parenthetical asides removed.

    This chat model likes to restate a number it just spelled out: "deux (2)
    mois", "d'un (1) an". Run 3 failed both on a correct answer, because the
    interruption means the text contains neither "deux mois" nor "2 mois". The
    aside is not a different claim, so grading looks at this form too rather
    than making every expectation enumerate the habit."""
    return _PARENS.sub(" ", answer)


_WS = re.compile(r"\s+")
# typographic apostrophes/primes -> ASCII so markers like "n indique" match
# whether the model wrote « n'indique », « n’indique » or « n‛indique »
_APOS = str.maketrans({"'": " ", "’": " ", "ʼ": " ", "‘": " ",
                       "‛": " ", "′": " ", "`": " "})


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower()).translate(_APOS)
    s = "".join(" " if unicodedata.category(c) == "Zs" else c
                for c in s if not unicodedata.combining(c))
    return _WS.sub(" ", s)


def ask(api: str, kb_id: str, question: str) -> tuple[str, list[dict], dict | None]:
    answer, citations, verification = "", [], None
    with httpx.Client(base_url=api, timeout=180) as client:
        with client.stream("POST", f"/api/kbs/{kb_id}/chat",
                           json={"question": question}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if event["type"] == "token":
                    answer += event["content"]
                elif event["type"] == "citations":
                    citations = event["citations"]
                elif event["type"] == "done":
                    verification = event.get("verification")
                elif event["type"] == "error":
                    raise RuntimeError(event["message"])
    return answer, citations, verification


def grade(item: dict, answer: str, citations: list[dict],
          verification: dict | None) -> tuple[bool, str]:
    # grade what the answer ASSERTS: dumped table rows are evidence the model
    # pasted, not a claim it made (run 2 had answers stating the wrong cell in
    # prose while pasting a grid containing the right string)
    claim = _norm(prose_only(answer))
    # the same claim with parenthetical asides dropped; an expectation may
    # match either form
    bare = _norm(without_asides(prose_only(answer)))
    if item.get("type") == "trap":
        if verification and verification.get("status") == "warnings":
            return True, "verification warned"
        if not citations:
            return True, "no sources asserted"
        if is_refusal(claim):
            return True, "refused honestly"
        return False, "answered a trap without warning (review by hand)"

    # a hedged/refusing answer cannot also be a correct one, even if the
    # expected string appears somewhere in a pasted table
    marker = refusal_marker(claim)
    if marker:
        return False, f"answer refuses/hedges instead of stating the value " \
                      f"(on «{marker}»)"
    # an expected entry may list acceptable surface forms separated by "|":
    # prose facts have several faithful wordings ("multi-acteurs" vs "de
    # multiples acteurs"), and only NUMBERS must be copied character-exact
    missing = [s for s in item.get("expected_answer_contains", [])
               if not any(_norm(variant) in claim or _norm(variant) in bare
                          for variant in s.split("|"))]
    if missing:
        return False, f"answer missing: {missing}"
    expected_doc = item.get("expected_doc")
    if expected_doc and not any(
            expected_doc.lower() in (c.get("filename") or "").lower()
            or (c.get("filename") or "").lower() in expected_doc.lower()
            for c in citations):
        return False, f"expected source not cited: {expected_doc}"
    return True, "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True, help="knowledge base id to query")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--questions", type=Path,
                    default=Path(__file__).parent / "questions.jsonl")
    args = ap.parse_args()

    if not args.questions.exists():
        sys.exit(f"{args.questions} not found — copy questions.example.jsonl "
                 "and fill it with real questions")
    items = [json.loads(line) for line in
             args.questions.read_text(encoding="utf-8").splitlines()
             if line.strip()]

    results: dict[str, list[bool]] = {}
    transcript: list[dict] = []
    print(f"{'id':6s} {'type':6s} {'verdict':8s} detail")
    print("-" * 72)
    for item in items:
        answer, citations, verification = "", [], None
        try:
            answer, citations, verification = ask(args.api, args.kb,
                                                  item["question"])
            ok, detail = grade(item, answer, citations, verification)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"error: {e}"
        results.setdefault(item.get("type", "text"), []).append(ok)
        transcript.append({**item, "ok": ok, "detail": detail,
                           "answer": answer,
                           "cited": [c.get("filename") for c in citations],
                           "verification": verification})
        print(f"{item.get('id', '?'):6s} {item.get('type', 'text'):6s} "
              f"{'PASS' if ok else 'FAIL':8s} {detail}")
        if not ok:
            snippet = " ".join(answer.split())[:220]
            print(f"       answer: {snippet}{'…' if len(answer) > 220 else ''}")
            if item.get("expected_doc"):
                # how many blocks the answer was built from tells you which
                # retrieval path ran: rerank_top_k (8) when the reranker is
                # working, retrieve_top_k (12) when it is off or unreachable
                print(f"       cited : {len(citations)} blocks "
                      f"{[c.get('filename') for c in citations]}")

    # named after the dataset: two question sets against two KBs must not
    # overwrite each other's transcript, which is the only record of WHY an
    # item failed
    out_path = Path(__file__).parent / "results" / f"{args.questions.stem}.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in transcript),
        encoding="utf-8")
    print(f"\nfull transcript: {out_path}")

    print("-" * 72)
    exit_code = 0
    for qtype, oks in sorted(results.items()):
        rate = sum(oks) / len(oks)
        target = 1.0 if qtype == "trap" else 0.95
        verdict = "PASS" if rate >= target else "FAIL"
        if verdict == "FAIL":
            exit_code = 1
        print(f"{qtype:6s}: {sum(oks)}/{len(oks)} = {rate:.0%} "
              f"(target >= {target:.0%}: {verdict})")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

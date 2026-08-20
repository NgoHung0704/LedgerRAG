"""`make eval-qa` — the answer-quality gate (SPEC Phase 4 §5).

Feeds real questions through the LIVE query pipeline (API SSE endpoint) and
grades three things per question type:

- table/text: every `expected_answer_contains` string appears in the answer
- contrast: the corpus holds several editions THAT DISAGREE, so refusing OR
  naming at least two of the listed markers passes; picking one silently fails
  AND `expected_doc` is among the citations (right answer FROM the right
  source).
- concordant: several editions cover the subject and AGREE. The mirror of
  contrast, and it grades refusal the other way: refusing FAILS, because there
  is no ambiguity to be honest about. Passes when every listed string is
  stated and at least two sources are cited — one citation means the answer
  picked an edition instead of showing they agree.
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


def chat_url(kb: str | None, assistant: str | None) -> str:
    """Where to send the questions: a knowledge base, or an assistant.

    The gates were built against `/api/kbs/{id}/chat`, which answers with the
    KB's config and the GLOBAL chat instructions. An assistant is a different
    thing — its own instructions, escalation contact, verify override and set
    of knowledge bases — and it is what a colleague actually types into. Both
    stream the same events, so only the path differs.

    Naming both, or neither, raises rather than picking one: a report whose
    header names a target that was never asked is worse than no report.
    """
    if bool(kb) == bool(assistant):
        raise ValueError("give exactly one of --kb / --assistant")
    return f"/api/kbs/{kb}/chat" if kb else f"/api/assistants/{assistant}/chat"


def cleanup_conversations(client, session_ids, keep: bool = False) -> tuple[int, int]:
    """Remove the chat threads this run created. Returns (deleted, failed).

    A question asked without a session_id mints a STORED conversation, so a
    39-question run leaves 39 threads in somebody's sidebar, indistinguishable
    from the ones they had on purpose. The harness cleans up after itself.

    This runs AFTER the score is printed, and that governs everything here: it
    never raises and never stops early. An exception escaping would abort the
    run and bury the numbers it exists to produce — so a failed delete is
    counted and reported, and the loop carries on.

    404 counts as cleaned: the thread is not there, which is the goal.
    """
    if keep:
        return (0, 0)
    deleted = failed = 0
    # dict.fromkeys de-duplicates and keeps order: the follow-up harness threads
    # ONE session through a conversation, so its id arrives once per graded turn
    for sid in dict.fromkeys(s for s in session_ids if s):
        try:
            response = client.delete(f"/api/conversations/{sid}")
            if response.status_code in (204, 404):
                deleted += 1
            else:
                failed += 1
        except Exception:  # noqa: BLE001 — see the docstring: never raise here
            failed += 1
    return deleted, failed


def ask(api: str, url: str,
        question: str) -> tuple[str, list[dict], dict | None, list[dict], str | None]:
    answer, citations, verification, see_also = "", [], None, []
    session_id = None
    with httpx.Client(base_url=api, timeout=180) as client:
        with client.stream("POST", url,
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
                    see_also = event.get("see_also") or []
                    session_id = event.get("session_id")
                elif event["type"] == "error":
                    raise RuntimeError(event["message"])
    return answer, citations, verification, see_also, session_id


def cites(citations: list[dict], doc: str | None,
          page: int | None) -> bool:
    """Was this source actually used? Filename matches either way round (the
    dataset may name it without its extension), and a page pins WHICH part."""
    for citation in citations:
        name = (citation.get("filename") or "").lower()
        if doc and not (doc.lower() in name or name in doc.lower()):
            continue
        if page is not None and citation.get("page") != page:
            continue
        return True
    return False


def cited_pages(citations: list[dict], doc: str | None) -> list[int]:
    return sorted({c.get("page") for c in citations
                   if not doc or (doc.lower() in (c.get("filename") or "").lower())
                   if c.get("page") is not None})


def grade(item: dict, answer: str, citations: list[dict],
          verification: dict | None,
          see_also: list[dict] | None = None) -> tuple[bool, str]:
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

    if item.get("type") == "contrast":
        # Several editions of the same table sit in the corpus, so the question
        # has more than one correct answer. Refusing is fine. Naming the
        # versions is BETTER — it is what OVERLAP_RULE asks for. Silently
        # picking one is the failure.
        #
        # Graded as a trap, those good answers scored FAIL: the trap grader
        # passes only on refusal, so the metric fell while the product improved.
        # Here the pass condition is "said enough to let a reader tell which
        # version this is": at least TWO of the listed markers, since one names
        # a version and two name a choice.
        if is_refusal(claim):
            return True, "refused honestly"
        named = [s for s in item.get("expected_answer_contains", [])
                 if any(_norm(variant) in claim or _norm(variant) in bare
                        for variant in s.split("|"))]
        if len(named) >= 2:
            return True, f"attributed ({', '.join(named)})"
        return False, (f"stated one version without naming the alternatives "
                       f"(named: {named or 'nothing'})")

    if item.get("type") == "concordant":
        # The mirror of `contrast`: several editions cover this subject and they
        # AGREE. Refusing is graded as a failure here, which is the opposite of
        # every other type in this file — deliberately. Elsewhere a refusal is
        # honesty about a real ambiguity; here there is none to be honest about,
        # and the corpus answers plainly.
        #
        # Citing a single source also fails. The value alone does not show the
        # editions agree — an answer that read one edition and ignored the rest
        # is indistinguishable from one that checked, unless both are cited.
        # That is the whole behaviour this type exists to measure.
        if is_refusal(claim):
            return False, "refused although the sources agree"
        missing = [s for s in item.get("expected_answer_contains", [])
                   if not any(_norm(variant) in claim or _norm(variant) in bare
                              for variant in s.split("|"))]
        if missing:
            return False, f"did not state {', '.join(missing)}"
        if len(citations) < 2:
            return False, "stated it from a single source, so the editions " \
                          "were never shown to agree"
        return True, f"merged, {len(citations)} sources cited"

    if item.get("type") == "figure":
        # A chart, a diagram, a colour-coded scale. The assistant is NOT asked
        # to read these — it is asked to put the right one in front of a human,
        # who reads it. So the only thing graded is whether the right source
        # was retrieved: what the answer says about a picture is not the job,
        # and grading it would push the pipeline back towards analysing them.
        page = item.get("expected_page")
        if cites(citations, item.get("expected_doc"), page):
            return True, f"retrieved (page {page})" if page else "retrieved"
        # ...or offered in the see-also list, which is the OTHER way a figure
        # reaches the reader and the one built for it: a chart cannot be found
        # by ranking, since its numbers are in the drawing and its description
        # loses to the page's own prose. Grading citations alone would leave
        # this gate blind to the mechanism written to satisfy it.
        if cites(see_also or [], item.get("expected_doc"), page):
            return True, f"offered (page {page})" if page else "offered"
        seen = cited_pages(citations, item.get("expected_doc"))
        return False, (f"page {page} of {item.get('expected_doc')} was neither "
                       f"retrieved nor offered; pages cited from it: "
                       f"{seen or 'none'}")

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
    expected_page = item.get("expected_page")
    if expected_doc and not cites(citations, expected_doc, expected_page):
        where = f" page {expected_page}" if expected_page else ""
        return False, f"expected source not cited: {expected_doc}{where}"
    return True, "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--kb", help="knowledge base id to query")
    target.add_argument("--assistant",
                        help="assistant id to query instead — measures what "
                             "readers actually talk to, including its own "
                             "instructions and its whole set of KBs")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--keep-conversations", action="store_true",
                    help="leave the chat threads this run created in place "
                         "(default: delete them, so a 39-question run does "
                         "not fill somebody's sidebar with eval questions)")
    ap.add_argument("--questions", type=Path,
                    default=Path(__file__).parent / "questions.jsonl")
    args = ap.parse_args()

    if not args.questions.exists():
        sys.exit(f"{args.questions} not found — copy questions.example.jsonl "
                 "and fill it with real questions")
    items = [json.loads(line) for line in
             args.questions.read_text(encoding="utf-8").splitlines()
             if line.strip()]

    url = chat_url(args.kb, args.assistant)

    results: dict[str, list[bool]] = {}
    transcript: list[dict] = []
    # every question asked without a session_id mints a STORED conversation;
    # collected here so the run can remove its own litter afterwards
    sessions: list[str | None] = []
    print(f"target: {'assistant ' + args.assistant if args.assistant else 'kb ' + args.kb}")
    print(f"{'id':6s} {'type':6s} {'verdict':8s} detail")
    print("-" * 72)
    for item in items:
        answer, citations, verification, see_also = "", [], None, []
        try:
            answer, citations, verification, see_also, session_id = ask(
                args.api, url, item["question"])
            sessions.append(session_id)
            ok, detail = grade(item, answer, citations, verification, see_also)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"error: {e}"
        results.setdefault(item.get("type", "text"), []).append(ok)
        transcript.append({**item, "ok": ok, "detail": detail,
                           "answer": answer,
                           "cited": [c.get("filename") for c in citations],
                           "offered": [f"{v.get('filename')} p{v.get('page')}"
                                       for v in see_also],
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

    # Printed BEFORE the score table on purpose: the verdict is what a reader
    # came for, so it stays the last thing on screen.
    with httpx.Client(base_url=args.api, timeout=30) as client:
        removed, stuck = cleanup_conversations(
            client, sessions, keep=args.keep_conversations)
    if args.keep_conversations:
        print(f"kept {len([s for s in sessions if s])} conversation(s)")
    elif stuck:
        print(f"cleaned {removed} conversation(s); {stuck} could not be "
              f"removed — delete them by hand from the assistant's sidebar")
    elif removed:
        print(f"cleaned {removed} conversation(s) this run created")

    print("-" * 72)
    exit_code = 0
    for qtype, oks in sorted(results.items()):
        rate = sum(oks) / len(oks)
        # figures are a retrieval question, and retrieval is the harder half:
        # 0.95 on a handful of them would be a coin toss dressed as a gate
        target = {"trap": 1.0, "figure": 0.9}.get(qtype, 0.95)
        verdict = "PASS" if rate >= target else "FAIL"
        if verdict == "FAIL":
            exit_code = 1
        print(f"{qtype:6s}: {sum(oks)}/{len(oks)} = {rate:.0%} "
              f"(target >= {target:.0%}: {verdict})")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

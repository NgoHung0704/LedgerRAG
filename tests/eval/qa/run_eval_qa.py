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
import sys
import unicodedata
from pathlib import Path

import httpx

REFUSAL_MARKERS = [
    "ne contient", "ne figure", "pas disponible", "aucune information",
    "je ne sais", "not found", "no relevant", "không tìm thấy", "không có",
    "sources do not", "cannot answer", "je ne peux pas",
]


import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
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
    normalized = _norm(answer)
    if item.get("type") == "trap":
        if verification and verification.get("status") == "warnings":
            return True, "verification warned"
        if not citations:
            return True, "no sources asserted"
        if any(marker in normalized for marker in REFUSAL_MARKERS):
            return True, "refused honestly"
        return False, "answered a trap without warning (review by hand)"

    missing = [s for s in item.get("expected_answer_contains", [])
               if _norm(s) not in normalized]
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
    print(f"{'id':6s} {'type':6s} {'verdict':8s} detail")
    print("-" * 72)
    for item in items:
        try:
            answer, citations, verification = ask(args.api, args.kb,
                                                  item["question"])
            ok, detail = grade(item, answer, citations, verification)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"error: {e}"
        results.setdefault(item.get("type", "text"), []).append(ok)
        print(f"{item.get('id', '?'):6s} {item.get('type', 'text'):6s} "
              f"{'PASS' if ok else 'FAIL':8s} {detail}")

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

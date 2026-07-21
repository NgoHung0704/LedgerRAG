"""`make eval-routing` — the routing gate (SPEC Phase 5 §4).

Scores the LLMRouter SEPARATELY from answer quality, so a wrong answer can be
told apart from a wrong route (the two need different fixes). Feeds each
question to the multi-KB endpoint (POST /api/chat, auto-route) and compares the
KBs it chose against `expected_kbs`.

Two numbers, because they fail differently:
  - RECALL — did the route include every KB that holds the answer? A miss here
    is fatal: the answer is unreachable no matter how good the pipeline is.
  - EXACT — did the route choose exactly the expected set (SPEC DoD ≥ 90%)?
    Over-selection (recall ok, exact not) only costs a little relevance, since
    the reranker still filters — it is a tuning signal, not a dead end.

Questions file: JSONL with `expected_kbs` = a list of KB-name substrings, e.g.
    {"id": "r1", "question": "Combien de jours de congés ?",
     "expected_kbs": ["Règlement"]}
Lines without `expected_kbs` are skipped (they are answer-eval questions).

    python tests/eval/qa/run_eval_routing.py \
        [--api http://localhost:8000] [--questions .../routing.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


def grade_routing(expected_names: list[str],
                  routed_names: list[str]) -> tuple[bool, bool, str]:
    """(recall_ok, exact_ok, detail). A KB matches an expected entry when the
    entry is a case-insensitive substring of the KB name, so questions can name
    KBs loosely ("Règlement" for "Règlement intérieur")."""
    def matches(expected: str) -> bool:
        return any(expected.lower() in name.lower() for name in routed_names)

    def expected_for(name: str) -> bool:
        return any(e.lower() in name.lower() for e in expected_names)

    missing = [e for e in expected_names if not matches(e)]
    extra = [n for n in routed_names if not expected_for(n)]
    recall_ok = not missing
    exact_ok = recall_ok and not extra
    if missing:
        detail = f"MISSED {missing} (routed {routed_names})"
    elif extra:
        detail = f"over-selected {extra}"
    else:
        detail = "ok"
    return recall_ok, exact_ok, detail


def route(api: str, question: str) -> list[str]:
    """Ask the multi-KB endpoint to auto-route and return the chosen KB names."""
    id_to_name = {}
    with httpx.Client(base_url=api, timeout=120) as client:
        for kb in client.get("/api/kbs").raise_for_status().json():
            id_to_name[kb["id"]] = kb["name"]
        routed_ids: list[str] = []
        with client.stream("POST", "/api/chat",
                           json={"question": question}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if event["type"] == "done":
                    routed_ids = (event.get("routing") or {}).get("kb_ids", [])
                elif event["type"] == "error":
                    raise RuntimeError(event["message"])
    return [id_to_name.get(i, i) for i in routed_ids]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--questions", type=Path,
                    default=Path(__file__).parent / "questions.jsonl")
    args = ap.parse_args()

    items = [json.loads(line) for line in
             args.questions.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    routing_items = [it for it in items if it.get("expected_kbs")]
    if not routing_items:
        sys.exit("no questions carry `expected_kbs` — add routing questions "
                 "(needs several KBs; see SPEC Phase 5 DoD: 3 KBs, 10 questions)")

    recall_hits = exact_hits = 0
    print(f"{'id':6s} {'recall':7s} {'exact':6s} detail")
    print("-" * 72)
    for item in routing_items:
        try:
            routed = route(args.api, item["question"])
            recall_ok, exact_ok, detail = grade_routing(item["expected_kbs"], routed)
        except Exception as e:  # noqa: BLE001
            recall_ok, exact_ok, detail = False, False, f"error: {e}"
        recall_hits += recall_ok
        exact_hits += exact_ok
        print(f"{item.get('id', '?'):6s} {'OK' if recall_ok else 'MISS':7s} "
              f"{'OK' if exact_ok else '-':6s} {detail}")

    n = len(routing_items)
    print("-" * 72)
    print(f"recall (answer reachable): {recall_hits}/{n} = {recall_hits / n:.0%}")
    print(f"exact set (SPEC DoD >= 90%): {exact_hits}/{n} = {exact_hits / n:.0%}")
    # the gate is exact-set match; recall is reported because a recall miss is
    # the only fatal routing error (over-selection still answers)
    sys.exit(0 if exact_hits / n >= 0.90 else 1)


if __name__ == "__main__":
    main()

"""`make eval-followup` — the multi-turn gate (condense step).

A conversational follow-up is a fragment ("Et pour la classe 16 ?"). Stateless,
it retrieves the wrong table or nothing; with memory, CondenseQuestion folds the
thread into a standalone query first. This harness measures whether that fold
actually recovers the right answer.

Each line of the questions file is ONE conversation:

    {"id": "f4", "turns": [
        {"question": "Quel est le SMH de la classe d'emploi 11 ... ?"},
        {"question": "Et pour la classe 16 ?", "type": "table",
         "expected_answer_contains": ["52 000"], "expected_doc": "Avenant ...pdf"}]}

Turns run in order through the multi-KB endpoint (POST /api/chat, auto-route),
threading the session_id so the pipeline sees the history. A turn is GRADED only
if it carries `expected_answer_contains` — the opening turn is context-setting.
Grading reuses the exact eval-qa grader (right answer FROM the right source),
and the run prints what each follow-up was condensed to, so a miss shows whether
the fold was wrong or the answer was.

    python tests/eval/qa/run_eval_followup.py \
        [--api http://localhost:8000] [--questions .../followups.jsonl] [--ablate]

--ablate reruns each graded follow-up as a FRESH single turn (no history) and
reports the lift: how many the condense step recovered that a stateless ask
would have missed. That delta is the point of the feature.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

# reuse the eval-qa grader verbatim — a multi-turn answer is graded exactly like
# a single-turn one (right value, right source); only the ASKING differs
sys.path.insert(0, str(Path(__file__).parent))
from run_eval_qa import grade  # noqa: E402


def ask(client: httpx.Client, question: str, session_id: str | None,
        kb_ids: list[str] | None = None) -> dict:
    """One turn on the multi-KB endpoint. Returns answer + citations +
    verification + the session to continue + the condensed search query.

    kb_ids pins the search to specific KBs — this eval measures the CONDENSE
    step, so it holds routing constant (routing has its own gate, eval-routing);
    otherwise a routing miss would be scored as a memory miss."""
    body: dict = {"question": question}
    if session_id:
        body["session_id"] = session_id
    if kb_ids:
        body["kb_ids"] = kb_ids
    answer, citations, verification = "", [], None
    search_question, routed = question, []
    with client.stream("POST", "/api/chat", json=body) as response:
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
                session_id = event.get("session_id")
                search_question = event.get("search_question") or question
                routed = (event.get("routing") or {}).get("kb_ids", [])
            elif event["type"] == "error":
                raise RuntimeError(event["message"])
    return {"answer": answer, "citations": citations,
            "verification": verification, "session_id": session_id,
            "search_question": search_question, "routed": routed}


def resolve_pins(convo: dict, id_to_name: dict[str, str],
                 auto_route: bool) -> list[str] | None:
    """KB ids to pin for this conversation, from its `kbs` name-substrings
    (same loose matching as eval-routing). None = let the router decide."""
    if auto_route:
        return None
    wanted = convo.get("kbs") or []
    ids = [kid for want in wanted for kid, name in id_to_name.items()
           if want.lower() in name.lower()]
    return ids or None


def run_conversation(client: httpx.Client, convo: dict,
                     id_to_name: dict[str, str],
                     pins: list[str] | None) -> list[dict]:
    """Play a conversation turn by turn, threading the session. Returns one
    graded result per turn that carries expectations."""
    session_id: str | None = None
    graded: list[dict] = []
    for i, turn in enumerate(convo["turns"]):
        res = ask(client, turn["question"], session_id, kb_ids=pins)
        session_id = res["session_id"]
        if not turn.get("expected_answer_contains"):
            continue  # context-setting turn, not graded
        ok, detail = grade(turn, res["answer"], res["citations"],
                            res["verification"])
        condensed = res["search_question"]
        graded.append({
            "id": convo.get("id", "?"),
            "turn": i,
            "question": turn["question"],
            "ok": ok,
            "detail": detail,
            "condensed": condensed if condensed != turn["question"] else None,
            "routed": [id_to_name.get(k, k) for k in res["routed"]],
            "answer": res["answer"],
        })
    return graded


def ablate(client: httpx.Client, convo: dict,
           pins: list[str] | None) -> list[bool]:
    """Each graded follow-up asked cold, with NO history — the stateless
    baseline. Same KB pin as the threaded run, so the ONLY difference is memory:
    the gap between them is the lift condensing provides."""
    out: list[bool] = []
    for turn in convo["turns"]:
        if not turn.get("expected_answer_contains"):
            continue
        res = ask(client, turn["question"], None, kb_ids=pins)  # fresh session
        ok, _ = grade(turn, res["answer"], res["citations"], res["verification"])
        out.append(ok)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--questions", type=Path,
                    default=Path(__file__).parent / "followups.jsonl")
    ap.add_argument("--ablate", action="store_true",
                    help="also ask each follow-up cold (no history) to measure lift")
    ap.add_argument("--auto-route", action="store_true",
                    help="let the router pick the KB instead of pinning per "
                         "conversation (mixes routing into the score; use "
                         "eval-routing to test routing on its own)")
    args = ap.parse_args()

    if not args.questions.exists():
        sys.exit(f"{args.questions} not found")
    convos = [json.loads(line) for line in
              args.questions.read_text(encoding="utf-8").splitlines()
              if line.strip()]

    passed = total = 0
    ablate_pass = ablate_total = 0
    with httpx.Client(base_url=args.api, timeout=180) as client:
        id_to_name = {kb["id"]: kb["name"]
                      for kb in client.get("/api/kbs").raise_for_status().json()}
        mode = "auto-route" if args.auto_route else "KB pinned (routing held constant)"
        print(f"mode: {mode}")
        print(f"{'id':5s} {'verdict':8s} detail")
        print("-" * 72)
        for convo in convos:
            pins = resolve_pins(convo, id_to_name, args.auto_route)
            if not args.auto_route and pins is None:
                print(f"{convo.get('id', '?'):5s} {'SKIP':8s} "
                      f"no KB matched {convo.get('kbs')} — check the `kbs` field")
                continue
            try:
                results = run_conversation(client, convo, id_to_name, pins)
            except Exception as e:  # noqa: BLE001
                print(f"{convo.get('id', '?'):5s} {'ERROR':8s} {e}")
                total += 1
                continue
            for r in results:
                total += 1
                passed += r["ok"]
                print(f"{r['id']:5s} {'PASS' if r['ok'] else 'FAIL':8s} {r['detail']}")
                if r["condensed"]:
                    print(f"      condensed → {r['condensed']}  [routed: "
                          f"{', '.join(r['routed']) or '—'}]")
                if not r["ok"]:
                    snippet = " ".join(r["answer"].split())[:200]
                    print(f"      answer: {snippet}{'…' if len(r['answer']) > 200 else ''}")

            if args.ablate:
                try:
                    for ok in ablate(client, convo, pins):
                        ablate_total += 1
                        ablate_pass += ok
                except Exception:  # noqa: BLE001 — ablation is diagnostic, not the gate
                    pass

    print("-" * 72)
    if total == 0:
        sys.exit("no graded follow-up turns found")
    rate = passed / total
    if args.ablate and ablate_total:
        base = ablate_pass / ablate_total
        print(f"stateless baseline (no memory): {ablate_pass}/{ablate_total} = {base:.0%}")
        print(f"with memory (condense):         {passed}/{total} = {rate:.0%}")
        print(f"lift from remembering the thread: {rate - base:+.0%}")
        if not args.auto_route:
            # pinning does part of memory's job: a fragment keeps a specific
            # token ("classe 16", "Acheteur") that retrieves even without the
            # thread, so the cold baseline is inflated and the lift is muted /
            # noise-dominated (one flaky item swings it). Measure real lift here:
            print("note: KB is pinned — the cold baseline is inflated (the pin "
                  "pre-resolves ambiguity memory would). For the true user-facing "
                  "lift, run:  --ablate --auto-route")
    else:
        print(f"follow-ups answered correctly: {passed}/{total} = {rate:.0%}")
    # gate: a condensed follow-up is just an answer-quality question, so hold it
    # to the same spirit as eval-qa — near-perfect. iterate misses by hand.
    print(f"gate (>= 90%): {'PASS' if rate >= 0.90 else 'FAIL'}")
    sys.exit(0 if rate >= 0.90 else 1)


if __name__ == "__main__":
    main()

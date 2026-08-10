"""Run the parser-facing gates against a CANDIDATE model, without adopting it.

Two gates read the parser and nothing else: `eval-tables` grades a table cell by
cell through the production parsing path, `eval-figures` grades what gets read
off a chart. Everything else in the platform (retrieval, routing, answers) sees
a parser only through what it stored, so these two are the whole question when a
new parsing model is proposed.

The point of this script is that a candidate gets NUMBERS ON THIS CORPUS before
it gets a config change. A benchmark published with a model was measured on
someone else's documents; our documents are French insurance notices with
merged-cell tables and %BRSS values, and the gates already know what the right
answers are. So: point this at a served candidate, keep the config untouched,
and put the two scores beside the ones the current model gets.

    python scripts/eval_parser.py --at http://localhost:8010 \
        --model PaddlePaddle/PaddleOCR-VL

    python scripts/eval_parser.py --baseline     # same gates, config as-is

Subprocesses rather than imports on purpose: settings are read once per process,
so a patched os.environ in THIS process would not reliably reach the gate.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GATES = {
    "tables": ROOT / "tests" / "eval" / "tables" / "run_eval.py",
    "figures": ROOT / "tests" / "eval" / "figures" / "run_eval_figures.py",
}


def run(gate: str, env: dict[str, str]) -> int:
    script = GATES[gate]
    print(f"\n{'=' * 70}\n  {gate}: {script}\n{'=' * 70}", flush=True)
    return subprocess.run([sys.executable, str(script)], env=env, cwd=ROOT).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--at", help="base_url of the served candidate, "
                                 "e.g. http://localhost:8010")
    ap.add_argument("--model", help="model name the endpoint answers to")
    ap.add_argument("--provider", default="openai_compat",
                    choices=("ollama", "openai_compat"),
                    help="how to talk to it (default: openai_compat, i.e. vLLM)")
    ap.add_argument("--baseline", action="store_true",
                    help="run the same gates with the configured parser, so both "
                         "numbers come from the same corpus on the same day")
    ap.add_argument("--only", choices=sorted(GATES), action="append",
                    help="run one gate (repeatable); default is both")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.baseline:
        if args.at or args.model:
            ap.error("--baseline runs the CONFIGURED parser; drop --at/--model")
        print("parser: as configured (baseline)")
    else:
        if not (args.at and args.model):
            ap.error("give --at and --model, or --baseline")
        env["LEDGERRAG_MODELS__PARSER__PROVIDER"] = args.provider
        env["LEDGERRAG_MODELS__PARSER__BASE_URL"] = args.at
        env["LEDGERRAG_MODELS__PARSER__MODEL_NAME"] = args.model
        print(f"parser: {args.model} at {args.at} ({args.provider}) "
              f"- config on disk untouched")

    failed = [gate for gate in (args.only or sorted(GATES))
              if run(gate, env) != 0]
    if failed:
        print(f"\ngate(s) below target: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 0 spike: parse a table image with the configured `parser` VLM.

Standalone by design (no imports from tablerag/): this script is re-run every
time the parser model or the hardware changes, and must work before the
platform exists.

Usage:
    python spike/parse_table.py --image spike/tables/pivot_fr_auto/image.png
    python spike/parse_table.py --all           # every table under spike/tables/

Endpoint configuration (flags override env):
    --provider  ollama | openai_compat      [env LEDGERRAG_MODELS__PARSER__PROVIDER]
    --base-url  http://localhost:11434      [env LEDGERRAG_MODELS__PARSER__BASE_URL]
    --model     qwen2.5vl:7b                [env LEDGERRAG_MODELS__PARSER__MODEL_NAME]

Outputs, next to each image: parsed.json (validated result or honest failure)
and response.txt (raw model output). Prints tokens/s and warns when throughput
suggests CPU fallback (see SPEC Appendix A.3 for the RDNA4/ROCm pitfall).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt  # noqa: E402

# Below this, assume the model is not actually running on the GPU
# (RDNA4 + stock-Ollama ROCm 6.x silently falls back to CPU — Appendix A.3).
SUSPECT_CPU_TOKENS_PER_S = 5.0

FENCE_RE = re.compile(r"```(html|json)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

def call_ollama(base_url: str, model: str, image_b64: str, user_prompt: str,
                history: list[dict] | None = None) -> tuple[str, dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history or []
    messages.append({"role": "user", "content": user_prompt, "images": [image_b64]})
    r = httpx.post(f"{base_url.rstrip('/')}/api/chat",
                   json={"model": model, "messages": messages, "stream": False,
                         "options": {"temperature": 0}},
                   timeout=600)
    r.raise_for_status()
    data = r.json()
    stats = {
        "eval_count": data.get("eval_count"),
        "eval_duration_ns": data.get("eval_duration"),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "total_duration_ns": data.get("total_duration"),
    }
    if data.get("eval_count") and data.get("eval_duration"):
        stats["tokens_per_s"] = data["eval_count"] / (data["eval_duration"] / 1e9)
    return data["message"]["content"], stats


def call_openai_compat(base_url: str, model: str, image_b64: str, user_prompt: str,
                       history: list[dict] | None = None) -> tuple[str, dict]:
    api_key = env("LEDGERRAG_MODELS__PARSER__API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    content = [
        {"type": "text", "text": user_prompt},
        {"type": "image_url",
         "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
    ]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history or []
    messages.append({"role": "user", "content": content})
    r = httpx.post(f"{base_url.rstrip('/')}/v1/chat/completions",
                   headers=headers,
                   json={"model": model, "messages": messages, "temperature": 0},
                   timeout=600)
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    return data["choices"][0]["message"]["content"], {"usage": usage}


# --------------------------------------------------------------------------
# Output validation (contract: one ```html block + one ```json block)
# --------------------------------------------------------------------------

class ContractError(Exception):
    pass


def validate_response(text: str) -> dict[str, Any]:
    blocks = {kind.lower(): body for kind, body in FENCE_RE.findall(text)}
    if "html" not in blocks:
        raise ContractError("missing ```html block")
    if "json" not in blocks:
        raise ContractError("missing ```json block")
    try:
        payload = json.loads(blocks["json"])
    except json.JSONDecodeError as e:
        raise ContractError(f"json block is not valid JSON: {e}") from e
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ContractError('json block must be {"records": [...]} with >= 1 record')
    for i, rec in enumerate(records):
        for key in ("dimensions", "metrics", "raw_values"):
            if not isinstance(rec.get(key), dict):
                raise ContractError(f"record {i}: '{key}' must be an object")
        for k, v in rec["metrics"].items():
            if v is not None and not isinstance(v, (int, float)):
                raise ContractError(
                    f"record {i}: metric '{k}' must be a JSON number or null, got {v!r}")
    return {"html": blocks["html"].strip(), "records": records}


# --------------------------------------------------------------------------
# Main flow
# --------------------------------------------------------------------------

def parse_one(image_path: Path, provider: str, base_url: str, model: str,
              locale_hint: str) -> dict:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    call = call_ollama if provider == "ollama" else call_openai_compat

    user_prompt = build_user_prompt(locale_hint)
    t0 = time.monotonic()
    text, stats = call(base_url, model, image_b64, user_prompt)
    elapsed = time.monotonic() - t0

    raw_responses = [text]
    result: dict[str, Any]
    try:
        result = validate_response(text)
    except ContractError as first_error:
        # one retry with the concrete error message (spec Phase 2 §3)
        history = [{"role": "assistant", "content": text}]
        retry_prompt = build_user_prompt(locale_hint) + "\n\n" + build_retry_prompt(
            str(first_error))
        text2, stats2 = call(base_url, model, image_b64, retry_prompt, history=history)
        raw_responses.append(text2)
        stats = {"first": stats, "retry": stats2}
        try:
            result = validate_response(text2)
            result["retried"] = True
        except ContractError as second_error:
            # honest failure: keep everything, admit defeat (spec §0.3)
            result = {"error": f"contract violation after retry: {second_error}",
                      "first_error": str(first_error)}

    result["stats"] = stats
    result["elapsed_s"] = round(elapsed, 2)
    result["model"] = model
    result["provider"] = provider

    out_dir = image_path.parent
    (out_dir / "response.txt").write_text("\n\n=== RETRY ===\n\n".join(raw_responses),
                                          encoding="utf-8")
    (out_dir / "parsed.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    tps = stats.get("tokens_per_s") if isinstance(stats, dict) else None
    tps_msg = f"{tps:.1f} tok/s" if isinstance(tps, (int, float)) else "n/a"
    status = "FAILED (honest)" if "error" in result else \
        f"{len(result.get('records', []))} records"
    print(f"  {image_path.parent.name:24s} {status:20s} {elapsed:6.1f}s  {tps_msg}")
    if isinstance(tps, (int, float)) and tps < SUSPECT_CPU_TOKENS_PER_S:
        print(f"    !! {tps:.1f} tok/s — suspicious: model may be running on CPU. "
              f"Check `ollama ps` reports 100% GPU (SPEC Appendix A.3).")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, help="single table image to parse")
    ap.add_argument("--all", action="store_true",
                    help="parse every table under spike/tables/")
    ap.add_argument("--provider",
                    default=env("LEDGERRAG_MODELS__PARSER__PROVIDER", "ollama"),
                    choices=["ollama", "openai_compat"])
    ap.add_argument("--base-url",
                    default=env("LEDGERRAG_MODELS__PARSER__BASE_URL",
                                "http://localhost:11434"))
    ap.add_argument("--model",
                    default=env("LEDGERRAG_MODELS__PARSER__MODEL_NAME", "qwen2.5vl:7b"))
    ap.add_argument("--locale", default=None,
                    help="number-locale hint; defaults to ground_truth.json locale")
    args = ap.parse_args()

    if not args.image and not args.all:
        ap.error("provide --image PATH or --all")

    targets: list[Path] = []
    if args.all:
        tables_dir = Path(__file__).parent / "tables"
        targets = sorted(tables_dir.glob("*/image.png"))
        if not targets:
            sys.exit("no tables found — run `python spike/make_test_tables.py` first")
    else:
        targets = [args.image]

    print(f"parser endpoint: {args.provider} @ {args.base_url} model={args.model}\n")
    failures = 0
    for image_path in targets:
        locale = args.locale
        gt_path = image_path.parent / "ground_truth.json"
        if locale is None and gt_path.exists():
            locale = json.loads(gt_path.read_text(encoding="utf-8")).get("locale")
        try:
            result = parse_one(image_path, args.provider, args.base_url, args.model,
                               locale or "unknown")
            if "error" in result:
                failures += 1
        except (httpx.HTTPError, OSError) as e:
            failures += 1
            print(f"  {image_path.parent.name:24s} ERROR: {e}")

    print(f"\ndone: {len(targets) - failures}/{len(targets)} parsed. "
          f"Next: python spike/grade.py")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

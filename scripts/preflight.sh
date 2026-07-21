#!/usr/bin/env bash
# LedgerRAG deployment preflight (SPEC Phase 5 DoD + Appendix A).
#
# Checks a machine BEFORE/AFTER `docker compose up` and reports, in plain
# language, what an IT admin must fix. The headline check is the RDNA4 trap
# (Appendix A.3): Ollama on stock ROCm 6.x silently falls back to CPU on
# gfx1201 — the GPU is "detected" but inference runs on the CPU at a few
# tokens/s. We measure tokens/s and warn when it smells like CPU.
#
#   bash scripts/preflight.sh
# Honors the same env as the stack; override the endpoint it probes with
#   OLLAMA_URL=http://host:11434 CHAT_MODEL=qwen2.5:14b bash scripts/preflight.sh

set -uo pipefail

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; WARN=$((WARN + 1)); }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
head() { printf '\n\033[1m%s\033[0m\n' "$1"; }
WARN=0
FAIL=0

OLLAMA_URL="${OLLAMA_URL:-${LEDGERRAG_MODELS__CHAT__BASE_URL:-http://localhost:11434}}"
CHAT_MODEL="${CHAT_MODEL:-${LEDGERRAG_MODELS__CHAT__MODEL_NAME:-qwen2.5:14b}}"
API_URL="${API_URL:-http://localhost:8000}"
MIN_TOK_S="${MIN_TOK_S:-10}"   # below this, suspect CPU fallback

head "Host tooling"
if command -v docker >/dev/null 2>&1; then
  pass "docker $(docker --version | awk '{print $3}' | tr -d ',')"
  docker compose version >/dev/null 2>&1 \
    && pass "docker compose available" \
    || fail "docker compose plugin missing — install it (compose v2)"
else
  fail "docker not found — install Docker Engine"
fi

head "GPU"
if command -v nvidia-smi >/dev/null 2>&1; then
  name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
  pass "NVIDIA GPU: ${name:-detected}"
elif command -v rocminfo >/dev/null 2>&1; then
  gfx=$(rocminfo 2>/dev/null | grep -m1 -o 'gfx[0-9a-f]*')
  pass "AMD GPU via ROCm: ${gfx:-detected}"
  if [ "$gfx" = "gfx1201" ]; then
    warn "gfx1201 (RDNA4): stock Ollama ships ROCm 6.x and will SILENTLY fall "
    warn "  back to CPU. Use OLLAMA_VULKAN=1 or a ROCm 7 build (Appendix A.3)."
  fi
else
  warn "no nvidia-smi or rocminfo — GPU cannot be verified from here (may be "
  warn "  in another container). The tokens/s probe below is the real test."
fi

head "Model endpoint: $OLLAMA_URL"
if curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  pass "reachable"
  if curl -fsS "$OLLAMA_URL/api/tags" 2>/dev/null | grep -q "\"$CHAT_MODEL\""; then
    pass "chat model '$CHAT_MODEL' is installed"
  else
    warn "chat model '$CHAT_MODEL' not found — 'ollama pull $CHAT_MODEL'"
  fi

  # the RDNA4 trap: time a short generation, derive tokens/s
  printf '  … timing a short generation (this is the CPU-fallback test)\n'
  resp=$(curl -fsS --max-time 120 "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$CHAT_MODEL\",\"prompt\":\"Count to twenty.\",\"stream\":false}" 2>/dev/null)
  ec=$(printf '%s' "$resp" | grep -o '"eval_count":[0-9]*' | grep -o '[0-9]*')
  ed=$(printf '%s' "$resp" | grep -o '"eval_duration":[0-9]*' | grep -o '[0-9]*')
  if [ -n "$ec" ] && [ -n "$ed" ] && [ "$ed" -gt 0 ]; then
    toks=$(awk "BEGIN{printf \"%.1f\", $ec / ($ed/1000000000)}")
    if awk "BEGIN{exit !($toks < $MIN_TOK_S)}"; then
      fail "only ${toks} tok/s — this is CPU-fallback territory. On AMD see "
      fail "  Appendix A.3; verify 'ollama ps' shows 100% GPU, not CPU."
    else
      pass "${toks} tok/s — GPU inference looks healthy"
    fi
  else
    warn "could not measure tokens/s (unexpected response shape)"
  fi
else
  fail "unreachable — is the model server up and bound to 0.0.0.0? (a service "
  fail "  bound to 127.0.0.1 is not reachable from the api container)"
fi

head "LedgerRAG API: $API_URL"
if curl -fsS --max-time 5 "$API_URL/api/health/models" >/dev/null 2>&1; then
  bad=$(curl -fsS "$API_URL/api/health/models" 2>/dev/null \
    | grep -o '"ok":false' | wc -l | tr -d ' ')
  if [ "$bad" = "0" ]; then
    pass "all model roles report healthy"
  else
    warn "$bad model role(s) unhealthy — see $API_URL/api/health/models"
  fi
else
  warn "API not up yet (fine before 'docker compose up'); re-run after start"
fi

head "Summary"
if [ "$FAIL" -gt 0 ]; then
  printf '  \033[31m%d blocking issue(s)\033[0m, %d warning(s)\n' "$FAIL" "$WARN"
  exit 1
fi
if [ "$WARN" -gt 0 ]; then
  printf '  \033[33m%d warning(s)\033[0m — review before serving users\n' "$WARN"
  exit 0
fi
printf '  \033[32mall clear\033[0m\n'

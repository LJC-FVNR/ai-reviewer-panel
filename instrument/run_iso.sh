#!/usr/bin/env bash
set -uo pipefail
export PATH="/path/to/workspace/.local/bin:$PATH"
SLOT="$1"; RUNNER="$2"; MODEL="$3"; PROMPT="$4"; OUT="$5"
# Effort tier is PINNED, not left to the CLI default, because the default moved under this study.
# The calibration baselines (2026-07-02) recorded "reasoning effort: xhigh"; codex v0.144.1 now
# defaults to "max", and the current gpt-5.5 backend REJECTS max outright ("Unsupported value: 'max'
# ... Supported values are: none, low, medium, high, xhigh", HTTP 400), so every codex slot failed
# with rc=1. Effort tier is part of reviewer identity, so silently accepting a new default would have
# made the R1/R2 variant reviews incomparable to their own baselines -- a confound with no trace in
# the JSON. Pin it to what the baselines used and the pairing holds.
CODEX_EFFORT="${CODEX_EFFORT:-xhigh}"
ISO=$(mktemp -d); cd "$ISO"
if [ "$RUNNER" = "codex" ]; then
  cat "$PROMPT" | timeout 1500 codex exec --skip-git-repo-check \
      -c model_reasoning_effort="$CODEX_EFFORT" --model "$MODEL" - > "$OUT" 2>"${OUT}.err"; RC=$?
else
  cat "$PROMPT" | timeout 1500 claude --model "$MODEL" -p > "$OUT" 2>"${OUT}.err"; RC=$?
fi
echo "$RC" > "${OUT}.rc"; rm -rf "$ISO"; exit $RC

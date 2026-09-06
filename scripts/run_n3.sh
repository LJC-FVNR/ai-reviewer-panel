#!/usr/bin/env bash
# run_n3.sh — N3: the drift control N2 needs. 8 papers x 8 slots x 1 panel = 64 reviews of BYTE-IDENTICAL
# baseline text, scored on the same gateway, in the same session, immediately after N2's variants.
#
# WHY IT EXISTS. N2 differences a variant scored tonight against a baseline this roster scored in an earlier
# session (N0), exactly as section 6's five-model arm does. Any level shift in the provider between the two
# sessions therefore lands inside the delta and is indistinguishable from the treatment: all three of N2's
# transforms came out negative, and a common negative offset is what a between-session drift looks like. The
# control is to re-score the untouched text now and measure that offset directly, on the only text for which
# the treatment effect is known to be zero.
#
#   drift            = median over 8 papers of (N3 composite - N0 two-panel baseline composite)
#   corrected delta  = raw delta - drift
#
# The manuscripts are pia_variants/<id>/baseline.txt, verified sha256-identical to the files N0 scored, so a
# non-zero drift cannot be an extraction difference. Prompt, models file, mu and sigma are N2's, unchanged.
#
# Resumable: a parsed <slot>.json is never re-spent.
#
# Usage: run_n3.sh [--paper-jobs 4] [--timeout 1800]
set -uo pipefail
export PATH="/path/to/workspace/.local/bin:$PATH"

WS="/path/to/workspace"
CAL="$WS/paper_direction_98_calibration"
PROMPT="$CAL/ICLR/reviewer_prompt_iclr.md"
CP="$WS/paper_direction_72/cursor_panel"
MODELS="$CP/panel_models.json"
VAR="$WS/ai_native_academia/pia_variants"
N0="$WS/ai_native_academia/n0_cursor8_iclr"
OUT="$WS/ai_native_academia/n3_drift_cursor8"
LOG="$OUT/n3.log"
PAPER_JOBS=4; TMO=1800

while [ $# -gt 0 ]; do case "$1" in
  --paper-jobs) PAPER_JOBS="$2"; shift 2;;
  --timeout)    TMO="$2"; shift 2;;
  -h|--help)    sed -n '1,22p' "$0"; exit 0;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done

mkdir -p "$OUT/reviews" "$OUT/inputs"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG" >&2; }
[ -s "$PROMPT" ] || { echo "ERROR: prompt missing: $PROMPT" >&2; exit 2; }

# --- Stage, asserting the bytes are the bytes N0 scored ------------------------------------------------
JOBS=()
for d in "$VAR"/*/; do
  id="$(basename "$d")"
  [ -s "$d/baseline.txt" ] || continue
  [ -s "$N0/reviews/$id/panel1/C1.json" ] || { log "SKIP $id: no cursor8 baseline in N0"; continue; }
  a="$(sha256sum "$d/baseline.txt" | cut -d' ' -f1)"
  b="$(sha256sum "$N0/inputs/$id/manuscript_extracted.txt" | cut -d' ' -f1)"
  if [ "$a" != "$b" ]; then
    log "FATAL: $id baseline.txt is not the text N0 scored ($a vs $b) — a drift control on different bytes"
    log "       measures extraction, not drift."
    exit 2
  fi
  mkdir -p "$OUT/inputs/$id"
  ln -sfn "$d/baseline.txt" "$OUT/inputs/$id/manuscript_extracted.txt"
  JOBS+=("$id")
done
[ ${#JOBS[@]} -gt 0 ] || { log "FATAL: no jobs staged"; exit 2; }
log "N3 start: ${#JOBS[@]} papers x 8 slots = $(( ${#JOBS[@]} * 8 )) reviews of byte-identical text"

if ! bash "$CP/verify_models.sh" "$MODELS" >"$OUT/model_verification.txt" 2>&1; then
  log "FATAL: model preflight failed — see $OUT/model_verification.txt"
  exit 2
fi
log "preflight PASS: all 8 slots resolvable ($(date -u +%FT%TZ))"
export CURSOR_PANEL_SKIP_PREFLIGHT=1
LAST_SLOT="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['panel'][-1]['slot'])" "$MODELS")"

running=0; launched=0; skipped=0
for id in "${JOBS[@]}"; do
  rdir="$OUT/reviews/$id"
  if [ -s "$rdir/panel1/$LAST_SLOT.json" ]; then skipped=$((skipped+1)); continue; fi
  mkdir -p "$rdir"
  log "  [run ] $id"
  ( bash "$CP/run_cursor_panel.sh" \
        --manuscript "$OUT/inputs/$id/manuscript_extracted.txt" \
        --template "$PROMPT" \
        --models "$MODELS" \
        --out "$rdir" --panels 1 --label "n3_$id" --jobs 8 --timeout "$TMO" \
        >"$rdir.log" 2>&1 \
    || echo "[$(date +%H:%M:%S)]   WARN: $id had parse/contamination warnings (see $rdir.log)" >>"$LOG" ) &
  launched=$((launched+1)); running=$((running+1))
  if [ "$running" -ge "$PAPER_JOBS" ]; then wait -n 2>/dev/null || true; running=$((running-1)); fi
done
wait
log "all jobs finished (launched=$launched skipped=$skipped)"

python3 - "$OUT/reviews" "$MODELS" <<'PY' | tee -a "$LOG"
import glob, json, os, sys
root, models = sys.argv[1], sys.argv[2]
slots = [s["slot"] for s in json.load(open(models))["panel"]]
papers = sorted({p.split("/")[-2] for p in glob.glob(f"{root}/*/panel1")})
holes = [(p, s) for p in papers for s in slots
         if not (os.path.exists(f"{root}/{p}/panel1/{s}.json") and os.path.getsize(f"{root}/{p}/panel1/{s}.json") > 2)]
print(f"completeness: {len(papers)*len(slots)-len(holes)}/{len(papers)*len(slots)} reviews parsed")
if holes:
    print("  missing: " + ", ".join(f"{p}/{s}" for p, s in holes[:16]))
    print("  A hole makes the drift estimate rest on a different slot set than the delta it corrects.")
PY

log "N3 done. Next: n2_analyze.py — it picks the control up automatically and reports corrected deltas."

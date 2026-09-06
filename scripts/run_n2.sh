#!/usr/bin/env bash
# run_n2.sh — N2: the presentation-invariance audit run again on a roster that shares no vendor with the
# panel the transforms were measured against. 8 papers x 3 transforms x 8 slots x 1 panel = 192 reviews.
#
# WHY THIS ARM AND NOT A BIGGER ONE:
#   §6 measures what a mechanical, semantics-preserving edit is worth on the five-model panel. The reading a
#   venue would act on is "use several vendors and the effect washes out". That is a claim about a different
#   panel, so it cannot be answered by any amount of extra data on this one. The decision rule was fixed
#   before the run: a same-signed delta on both rosters means vendor diversity is NOT a
#   defence and the recommendation must be struck from §9; a delta that vanishes makes it a partial
#   mitigation and §9 says exactly that. Either way the paper changes, which is what makes it worth running.
#
# WHAT KEEPS THE DELTA A DELTA:
#   baseline    already scored, and by this same roster: the 8 papers are a subset of N0's 16, so their
#               cursor8 composites exist at n0_cursor8_iclr/reviews/<id>/panel*/C?.json. This arm adds only
#               the 3 variants per paper. A baseline scored by a different roster would make the delta a
#               roster difference.
#   instrument  variants are z-scored against the mu/sd already fitted in
#               calibration_params_cursor8_iclr.json. Refitting on the variants would let the treatment move
#               the yardstick it is measured with, which absorbs the effect being looked for.
#   prompt      reviewer_prompt_iclr.md, the same file byte-for-byte. The manuscript bytes are the only
#               thing that differs between a baseline and a variant, and between this roster and the other.
#   text        the SAME variant files N1 scored, from pia_variants/. Regenerating them would confound the
#               roster contrast with a transform re-run.
#
# QUEUE ORDER IS PART OF THE DESIGN. This queue drains over tens of minutes against a commercial gateway,
# and provider behaviour drifts within a day, so a transform-blocked queue would make scoring time a
# covariate of condition. The 24 (paper, transform) jobs are therefore shuffled with a fixed seed:
# reproducible, and not in label order.
#
# Resumable: a parsed <slot>.json is never re-spent.
#
# Usage: run_n2.sh [--paper-jobs 4] [--timeout 1800] [--limit N]
set -uo pipefail
export PATH="/path/to/workspace/.local/bin:$PATH"

WS="/path/to/workspace"
CAL="$WS/paper_direction_98_calibration"
PROMPT="$CAL/ICLR/reviewer_prompt_iclr.md"
CP="$WS/paper_direction_72/cursor_panel"
MODELS="$CP/panel_models.json"
VAR="$WS/ai_native_academia/pia_variants"
N0="$WS/ai_native_academia/n0_cursor8_iclr"
OUT="$WS/ai_native_academia/n2_pia_cursor8"
LOG="$OUT/n2.log"
PAPER_JOBS=4; TMO=1800; LIMIT=0
VARIANTS=(T1_endmatter T2_concede T3_lengthen)

while [ $# -gt 0 ]; do case "$1" in
  --paper-jobs) PAPER_JOBS="$2"; shift 2;;
  --timeout)    TMO="$2"; shift 2;;
  --limit)      LIMIT="$2"; shift 2;;
  -h|--help)    sed -n '1,33p' "$0"; exit 0;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done

mkdir -p "$OUT/reviews" "$OUT/inputs"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG" >&2; }

[ -s "$PROMPT" ] || { echo "ERROR: prompt missing: $PROMPT" >&2; exit 2; }
# The baseline this arm differences against has to already exist, by this roster. Without it a delta has
# nothing to subtract and the run would be 192 reviews of nothing in particular.
if [ ! -s "$N0/calibration_params_cursor8_iclr.json" ]; then
  echo "ERROR: no cursor8 parameters at $N0 — run run_n0.sh to completion first. N2 differences against" >&2
  echo "       N0's baselines and standardises with N0's mu/sd; neither exists yet." >&2
  exit 2
fi

# --- Stage the variant texts, symlinked so the reviewed bytes are provably N1's bytes -------------
JOBS=()
for d in "$VAR"/*/; do
  id="$(basename "$d")"
  [ -s "$d/baseline.txt" ] || continue
  # Only papers this roster has a baseline for, or the delta is cross-roster.
  [ -s "$N0/reviews/$id/panel1/C1.json" ] || { log "SKIP $id: no cursor8 baseline in N0"; continue; }
  for v in "${VARIANTS[@]}"; do
    [ -s "$d/$v.txt" ] || { log "FATAL: missing variant $id/$v.txt"; exit 2; }
    mkdir -p "$OUT/inputs/$id/$v"
    ln -sfn "$d/$v.txt" "$OUT/inputs/$id/$v/manuscript_extracted.txt"
    JOBS+=("$id/$v")
  done
done
[ ${#JOBS[@]} -gt 0 ] || { log "FATAL: no jobs staged"; exit 2; }

# Fixed-seed shuffle: interleaves transforms so condition is not confounded with position in the queue.
mapfile -t JOBS < <(printf '%s\n' "${JOBS[@]}" | python3 -c '
import random, sys
j = [l.strip() for l in sys.stdin if l.strip()]
random.Random(20260830).shuffle(j)
print("\n".join(j))')
if [ "$LIMIT" -gt 0 ] && [ "$LIMIT" -lt "${#JOBS[@]}" ]; then
  JOBS=("${JOBS[@]:0:$LIMIT}")
  log "NOTE: --limit $LIMIT => SUBSET. A subset is not N2; do not report it as one."
fi
log "N2 start: ${#JOBS[@]} (paper, transform) jobs x 8 slots = $(( ${#JOBS[@]} * 8 )) reviews (paper_jobs=$PAPER_JOBS)"

# --- Preflight once ------------------------------------------------------------------------------
if ! bash "$CP/verify_models.sh" "$MODELS" >"$OUT/model_verification.txt" 2>&1; then
  log "FATAL: model preflight failed — see $OUT/model_verification.txt"
  cat "$OUT/model_verification.txt" >&2
  exit 2
fi
log "preflight PASS: all 8 slots resolvable ($(date -u +%FT%TZ))"
export CURSOR_PANEL_SKIP_PREFLIGHT=1
LAST_SLOT="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['panel'][-1]['slot'])" "$MODELS")"

# --- Review ---------------------------------------------------------------------------------------
running=0; launched=0; skipped=0
for job in "${JOBS[@]}"; do
  rdir="$OUT/reviews/$job"
  if [ -s "$rdir/panel1/$LAST_SLOT.json" ]; then skipped=$((skipped+1)); continue; fi
  mkdir -p "$rdir"
  log "  [run ] $job"
  ( bash "$CP/run_cursor_panel.sh" \
        --manuscript "$OUT/inputs/$job/manuscript_extracted.txt" \
        --template "$PROMPT" \
        --models "$MODELS" \
        --out "$rdir" --panels 1 --label "${job//\//_}" --jobs 8 --timeout "$TMO" \
        >"$rdir.log" 2>&1 \
    || echo "[$(date +%H:%M:%S)]   WARN: $job had parse/contamination warnings (see $rdir.log)" >>"$LOG" ) &
  launched=$((launched+1)); running=$((running+1))
  if [ "$running" -ge "$PAPER_JOBS" ]; then wait -n 2>/dev/null || true; running=$((running-1)); fi
done
wait
log "all jobs finished (launched=$launched skipped=$skipped)"

# --- Completeness, before any delta is computed ---------------------------------------------------
python3 - "$OUT/reviews" "$MODELS" <<'PY' | tee -a "$LOG"
import glob, json, os, sys
root, models = sys.argv[1], sys.argv[2]
slots = [s["slot"] for s in json.load(open(models))["panel"]]
jobs = sorted({"/".join(p.split("/")[-3:-1]) for p in glob.glob(f"{root}/*/*/panel1")})
holes = [(j, s) for j in jobs for s in slots
         if not (os.path.exists(f"{root}/{j}/panel1/{s}.json") and os.path.getsize(f"{root}/{j}/panel1/{s}.json") > 2)]
n = len(jobs) * len(slots) - len(holes)
print(f"completeness: {n}/{len(jobs) * len(slots)} reviews parsed ({len(jobs)} jobs x {len(slots)} slots)")
if holes:
    by = {}
    for j, s in holes:
        by[s] = by.get(s, 0) + 1
    print("  missing: " + ", ".join(f"{s} {c}" for s, c in sorted(by.items())))
    print("  A hole is not neutral here: a variant missing the slot its baseline has makes that paper's")
    print("  delta a comparison between different rosters. Re-run (it resumes) before analysing.")
PY

log "N2 done. Next: n2_analyze.py — delta against N0 baselines, cursor8 mu/sd, sign test over 8 papers."

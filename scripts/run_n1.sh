#!/usr/bin/env bash
# run_n1.sh — N1: the presentation-invariance audit on the 5-model panel.
# Every accepted paper with a de-identified text x 3 transforms x 5 slots x 2 panels, less whatever
# cells the gate drops below its strength floor. It is the run the presentation-invariance study reads.
#
# WHAT MAKES THIS A WITHIN-PAPER DELTA AND NOT A NEW CALIBRATION:
#   baseline    already scored. The 16 accepted papers' 5-model reviews live in $CAL/reviews, and
#               their composites are in calibration_params_portable.json:per_paper_composite. This
#               run adds ONLY the 3 variants per paper, so the baseline arm costs 0 reviews.
#   instrument  variants are z-scored against the EXISTING mu/sd in that params file. Refitting on
#               the variants would let the treatment move the yardstick it is being measured with,
#               absorbing the very effect we are trying to see.
#   prompt      reviewer_prompt_iclr.md, VERBATIM, the same file the baselines used. The manuscript
#               bytes are the only thing that differs between baseline and variant.
#
# QUEUE ORDER IS PART OF THE DESIGN. Jobs are interleaved across transforms, never blocked by
# transform: this queue drains over hours, provider behaviour drifts within a day, and a
# transform-blocked queue would make scoring time a covariate of condition. That failure mode is
# a known one and it is exactly this shape, so the queue is shuffled with a fixed seed
# (reproducible) rather than emitted in label order.
#
# Resumable: a parsed $slot.json is never re-spent.
#
# Usage: run_n1.sh [--jobs 8] [--panels 2] [--limit N]
set -uo pipefail
export PATH="/path/to/workspace/.local/bin:$PATH"

WS="/path/to/workspace"
CAL="$WS/paper_direction_98_calibration"
ICLR="$CAL/ICLR"
PROMPT_TMPL="$ICLR/reviewer_prompt_iclr.md"
RUN_ISO="$ICLR/run_iso.sh"
PARSE="$ICLR/parse_review.py"
VAR="$WS/ai_native_academia/pia_variants"
OUT="$WS/ai_native_academia/n1_pia_5model"
LOG="$OUT/n1.log"

MAXJOBS=8; PANELS=2; LIMIT=0
while [ $# -gt 0 ]; do case "$1" in
  --jobs)   MAXJOBS="$2"; shift 2;;
  --panels) PANELS="$2"; shift 2;;
  --limit)  LIMIT="$2"; shift 2;;
  -h|--help) sed -n '1,30p' "$0"; exit 0;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done

SLOTS=(
  "R1 codex gpt-5.5"
  "R2 codex gpt-5.4"
  "R3 claude us.anthropic.claude-opus-4-8[1m]"
  "R4 claude us.anthropic.claude-opus-4-7[1m]"
  "R5 claude us.anthropic.claude-sonnet-4-6[1m]"
)

[ -s "$PROMPT_TMPL" ] || { echo "ERROR: prompt missing: $PROMPT_TMPL" >&2; exit 2; }
[ -s "$VAR/manifest.json" ] || { echo "ERROR: no PIA variants; run pia_transforms.py --build" >&2; exit 2; }
mkdir -p "$OUT/reviews"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# --- The gate is a precondition, not a formality ------------------------------------------------
# Scoring an unverified variant set is how a transform that changed a number, or one that changed
# nothing, gets 240 reviews spent on it. Refuse rather than warn.
if ! python3 "$WS/ai_native_academia/pia_transforms.py" --verify "$VAR" >"$OUT/gate.txt" 2>&1; then
  log "FATAL: PIA gate FAILED — refusing to score. See $OUT/gate.txt"
  tail -20 "$OUT/gate.txt" >&2
  exit 2
fi
log "PIA gate PASS ($(grep -c . "$OUT/gate.txt") lines of evidence in gate.txt)"

build_prompt(){ # <variant_txt> <out_prompt>
  python3 - "$PROMPT_TMPL" "$1" "$2" <<'PY'
import sys
tmpl, mtxt, out = sys.argv[1:4]
t = open(tmpl).read()
m = open(mtxt, encoding='utf-8', errors='replace').read()
open(out, 'w').write(t.replace("{{MANUSCRIPT_TEXT}}", m))
PY
}

run_one(){ # <paper> <variant> <panel> <slot> <runner> <model>
  local pid="$1" v="$2" panel="$3" slot="$4" runner="$5" model="$6"
  local d="$OUT/reviews/${pid}__${v}/$panel"
  mkdir -p "$d"
  local js="$d/$slot.json"
  [ -s "$js" ] && return 0
  local mtxt="$VAR/$pid/$v.txt"
  [ -s "$mtxt" ] || { log "MISS $pid/$v — no variant text"; return 1; }
  local prompt="$d/$slot.prompt.txt" outf="$d/$slot.out"
  build_prompt "$mtxt" "$prompt"
  bash "$RUN_ISO" "$slot" "$runner" "$model" "$prompt" "$outf" >/dev/null 2>&1
  if python3 "$PARSE" --in "$outf" --out "$js" 2>>"$LOG"; then
    log "OK   $pid/$v/$panel/$slot"
  else
    log "FAIL $pid/$v/$panel/$slot (parse) rc=$(cat "${outf}.rc" 2>/dev/null)"
  fi
}
export -f run_one build_prompt log
export OUT VAR PROMPT_TMPL RUN_ISO PARSE LOG

# --- Emit the job list, then shuffle it with a fixed seed ---------------------------------------
JOBS="$OUT/jobs.txt"
python3 - "$VAR/manifest.json" "$PANELS" "$JOBS" <<'PY'
import json, random, sys
manifest, panels, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
m = json.load(open(manifest))
variants = [v for v in m["variants"][m["papers"][0]] if v != "baseline"]
# The gate's exclusion list is the authority on which cells exist. Reading it here rather than
# re-deriving the condition means the queue cannot disagree with the gate about the arm's size, and a
# cell the gate dropped cannot be scored by a queue that never heard about it.
drop = {(e["paper"], e["transform"]) for e in m.get("excluded", [])}
jobs = [f"{p}|{v}|panel{k}" for p in m["papers"] for v in variants for k in range(1, panels + 1)
        if (p, v) not in drop]
random.Random(20260830).shuffle(jobs)   # fixed seed: interleaved AND reproducible
open(out, "w").write("\n".join(jobs) + "\n")
print(f"{len(jobs)} paper-variant-panel units x 5 slots = {len(jobs)*5} reviews; "
      f"variants={variants}; {len(drop)} cell(s) excluded by the gate")
PY
log "queue: $(wc -l <"$JOBS") units (shuffled, seed 20260830)"

n=0
while IFS='|' read -r pid v panel; do
  [ -z "$pid" ] && continue
  n=$((n+1))
  if [ "$LIMIT" -gt 0 ] && [ "$n" -gt "$LIMIT" ]; then break; fi
  for s in "${SLOTS[@]}"; do
    set -- $s; slot=$1; runner=$2; model=$3
    while [ "$(jobs -rp | wc -l)" -ge "$MAXJOBS" ]; do sleep 2; done
    run_one "$pid" "$v" "$panel" "$slot" "$runner" "$model" &
  done
done < "$JOBS"
wait
log "=== N1 review pass done ==="

python3 - "$OUT/reviews" "$PANELS" <<'PY'
import glob, json, os, sys
root, panels = sys.argv[1], int(sys.argv[2])
slots = ["R1", "R2", "R3", "R4", "R5"]
units = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, "*")) if os.path.isdir(p))
have = miss = 0; holes = []
for u in units:
    for k in range(1, panels + 1):
        for s in slots:
            f = os.path.join(root, u, f"panel{k}", f"{s}.json")
            if os.path.exists(f) and os.path.getsize(f) > 2:
                have += 1
            else:
                miss += 1; holes.append(f"{u}/panel{k}/{s}")
print(f"completeness: {have}/{have+miss} reviews parsed over {len(units)} paper-variant units")
if holes:
    print(f"HOLES ({len(holes)}): " + ", ".join(holes[:20]) + (" ..." if len(holes) > 20 else ""))
PY
log "N1 done. Next: analyse_n1.py for per-transform delta vs the 0.160 z test-retest band."

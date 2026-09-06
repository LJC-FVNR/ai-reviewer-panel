#!/usr/bin/env bash
# run_n1b.sh — N1b: the drift control the FIVE-MODEL arm never had. Every paper in the presentation arm gets
# 2 panels of BYTE-IDENTICAL baseline text and 1 panel of each presentation variant, scored now, on the same
# runner and prompt as the variants. The paper list is the variant manifest's, so when that arm grew from half
# the accepted papers to all of them this arm grew with it: a drift control smaller than the arm it corrects
# would leave half the deltas taking their correction from the other half.
#
# WHY IT EXISTS, and why it is worth 80 reviews six days before a deadline.
#   Section 6's five-model deltas difference a variant scored on 2026-08-30 against a baseline scored during
#   calibration, days earlier. A level shift in either provider between those sessions lands inside every delta
#   and is indistinguishable from the treatment -- and all three transforms came out negative, which is what a
#   common negative offset looks like. N2b measured exactly this on the eight-slot roster (+0.037 z, inside the
#   band, POSITIVE, so drift was masking the effects there rather than making them). The roster the body argues
#   from has no such control, so its correction is borrowed from a different roster on a different gateway.
#   That is the one uncontrolled path from "presentation moved the score" to "the session moved the score".
#
#   A paired within-paper test needs it for a second reason. |variant - baseline| across a session boundary
#   contains treatment + noise + offset, while the re-run |panel1 - panel2| inside one session contains noise
#   alone, so comparing them credits the offset to the treatment. With this arm both sides of the comparison
#   cross the same boundary and the offset cancels by construction rather than by correction.
#
#   drift             = median over 8 papers of (N1b baseline composite - calibration two-panel composite)
#   same-session band = median over 8 papers of |N1b panel1 - N1b panel2|, this roster's re-run band measured
#                       now instead of assumed to be the calibration session's 0.160 z
#   exact paired test = |variant - drift panel1| against |drift panel2 - drift panel1|, same session on both
#                       sides, so swapping the two labels is a relabelling and nothing else
#
# TWO PANELS, not one. N2b took one panel because it only had to estimate an offset. This arm is also the
# noise side of an exact label-swap test, and a swap is only exact if both sides are the same estimator: one
# drift panel against two variant panels would put less noise in the treatment term than in the control term
# and quietly bias the test toward the paper's own conclusion.
#
# A SECOND PASS ADDS T2 AND A THIRD BASELINE PANEL (--pass2). T2 was left out while this arm was only a
# control on the presentation verdict, which T2 does not carry. It is in now because section 6 divides one
# arm's cost by another's: a ratio between a same-session number and a cross-session one is not a ratio of
# two costs, it is a ratio with a session boundary inside the denominator. T2 therefore has to be measured the
# way T1 is. It cannot simply be appended to the first queue, because a condition scored after every other
# condition has finished has its scoring time confounded with itself -- the defect this file's queue shuffle
# exists to prevent. So the second pass carries its own baseline panel, shuffled together with T2 over one
# queue, and T2's delta is taken against those panels: the control shares the treatment's queue positions.
# TWO of them, for the reason the first pass takes two: the label-swap test needs its noise term to be the
# same estimator as its treatment term, and a gap measured across the two passes is not that. They also
# price the pass boundary itself, which is the one thing a second pass introduces.
#
# AND IT RE-SCORES THE TWO PRESENTATION VARIANTS, one panel each, IN THE SAME QUEUE. Without that, this arm
# measures a drift across the calibration -> today boundary while section 6's deltas cross the calibration ->
# 2026-08-30 boundary: two different boundaries, so the offset would still have to be assumed exchangeable
# rather than cancelled. With it, the contrast |variant - drift| and the yardstick |drift panel1 - drift
# panel2| are both inside one session and the exact label swap needs no assumption at all. It is also the
# first within-roster replication of section 6's effect on a fresh session, which can come out against us.
#
# ONE SHUFFLED QUEUE OVER ALL THREE CONDITIONS, not one run per condition. Running the baselines first and the
# variants after would make scoring time a covariate of condition -- the failure mode that
# run_n1.sh already guards against. An earlier launch of this script had exactly that defect and was stopped
# after ten reviews; those ten are baseline reviews, they are kept, and a parsed slot is never re-spent.
#
# The manuscripts are pia_variants/<id>/baseline.txt, asserted sha256-identical to the deid/build_<id>/
# manuscript.txt the calibration reviews were scored on, so a non-zero drift cannot be an extraction change.
# Prompt, slots, mu and sigma are section 6's, unchanged: nothing about the instrument is re-chosen here.
#
# Queue order is shuffled with a fixed seed. This queue drains over half an hour and provider behaviour moves
# within a day; a paper-ordered queue would make scoring time a covariate of paper.
#
# Resumable: a parsed <slot>.json is never re-spent.
#
# Usage: run_n1b.sh [--jobs 8] [--panels 2] [--pass2]
set -uo pipefail
export PATH="/path/to/workspace/.local/bin:$PATH"

WS="/path/to/workspace"
CAL="$WS/paper_direction_98_calibration"
ICLR="$CAL/ICLR"
PROMPT_TMPL="$ICLR/reviewer_prompt_iclr.md"
RUN_ISO="$ICLR/run_iso.sh"
PARSE="$ICLR/parse_review.py"
AN="$WS/ai_native_academia"
VAR="$AN/pia_variants"
OUT="$AN/n1b_drift_5model"
LOG="$OUT/n1b.log"

MAXJOBS=8; PANELS=2; PASS=1
while [ $# -gt 0 ]; do case "$1" in
  --jobs)   MAXJOBS="$2"; shift 2;;
  --panels) PANELS="$2"; shift 2;;
  --pass2)  PASS=2; shift;;
  -h|--help) sed -n '1,38p' "$0"; exit 0;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done

SLOTS=(
  "R1 codex gpt-5.5"
  "R2 codex gpt-5.4"
  "R3 claude us.anthropic.claude-opus-4-8[1m]"
  "R4 claude us.anthropic.claude-opus-4-7[1m]"
  "R5 claude us.anthropic.claude-sonnet-4-6[1m]"
)

[ -s "$PROMPT_TMPL" ]        || { echo "ERROR: prompt missing: $PROMPT_TMPL" >&2; exit 2; }
[ -s "$VAR/manifest.json" ]  || { echo "ERROR: no PIA variants at $VAR" >&2; exit 2; }
mkdir -p "$OUT/reviews"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# --- The precondition: the text must be the text the baseline reviews were of ---------------------
# A drift control that scores a re-extracted manuscript measures the extractor, not the provider. Refuse.
python3 - "$VAR/manifest.json" "$VAR" "$CAL" <<'PY' || exit 2
import hashlib, json, sys
manifest, var, cal = sys.argv[1:4]
def h(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()
bad = []
for p in json.load(open(manifest))["papers"]:
    a, b = f"{var}/{p}/baseline.txt", f"{cal}/deid/build_{p}/manuscript.txt"
    try:
        if h(a) != h(b):
            bad.append(f"{p}: baseline.txt != the calibration manuscript")
    except OSError as e:
        bad.append(f"{p}: {e.strerror} ({e.filename})")
n = len(json.load(open(manifest))["papers"])
print(f"baseline identity: " + (f"all {n} sha256-identical to the scored text" if not bad else "FAIL"))
for x in bad:
    print("  " + x)
sys.exit(1 if bad else 0)
PY

build_prompt(){ # <manuscript> <out_prompt>
  python3 - "$PROMPT_TMPL" "$1" "$2" <<'PY'
import sys
tmpl, mtxt, out = sys.argv[1:4]
open(out, "w").write(open(tmpl).read().replace(
    "{{MANUSCRIPT_TEXT}}", open(mtxt, encoding="utf-8", errors="replace").read()))
PY
}

run_one(){ # <paper> <condition> <panel> <slot> <runner> <model>
  local pid="$1" cond="$2" panel="$3" slot="$4" runner="$5" model="$6"
  local d="$OUT/reviews/$pid/$cond/$panel"
  mkdir -p "$d"
  local js="$d/$slot.json"
  [ -s "$js" ] && return 0
  local mtxt="$VAR/$pid/$cond.txt"
  [ -s "$mtxt" ] || { log "MISS $pid/$cond -- no manuscript"; return 1; }
  local prompt="$d/$slot.prompt.txt" outf="$d/$slot.out"
  build_prompt "$mtxt" "$prompt"
  bash "$RUN_ISO" "$slot" "$runner" "$model" "$prompt" "$outf" >/dev/null 2>&1
  if python3 "$PARSE" --in "$outf" --out "$js" 2>>"$LOG"; then
    log "OK   $pid/$cond/$panel/$slot"
  else
    log "FAIL $pid/$cond/$panel/$slot (parse) rc=$(cat "${outf}.rc" 2>/dev/null)"
  fi
}
export -f run_one build_prompt log
export OUT VAR PROMPT_TMPL RUN_ISO PARSE LOG

JOBS="$OUT/jobs.txt"
[ "$PASS" = 2 ] && JOBS="$OUT/jobs_pass2.txt"
python3 - "$VAR/manifest.json" "$PANELS" "$JOBS" "$PASS" <<'PY'
import json, random, sys
manifest, panels, out, phase = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
papers = json.load(open(manifest))["papers"]
if phase == 1:
    # baseline twice (it is the noise yardstick and needs its own re-run), each presentation variant once.
    jobs = [f"{p}|baseline|panel{k}" for p in papers for k in range(1, panels + 1)]
    jobs += [f"{p}|{v}|panel1" for p in papers for v in ("T1_endmatter", "T3_lengthen")]
    seed = 20260831
else:
    # T2, and two more baseline panels shuffled in with it so the treatment and its control occupy the same
    # stretch of queue. Differencing T2 against pass one's baselines would compare a condition scored last
    # against controls scored first, which is the confound the shuffle is for.
    jobs = [f"{p}|T2_concede|panel1" for p in papers]
    jobs += [f"{p}|baseline|panel{panels + k}" for p in papers for k in (1, 2)]
    seed = 20260901
random.Random(seed).shuffle(jobs)
open(out, "w").write("\n".join(jobs) + "\n")
print(f"pass {phase}: {len(jobs)} paper-condition-panel units x 5 slots = {len(jobs) * 5} reviews")
PY
log "queue: $(wc -l <"$JOBS") units (pass $PASS, shuffled)"

while IFS='|' read -r pid cond panel; do
  [ -z "$pid" ] && continue
  for s in "${SLOTS[@]}"; do
    set -- $s
    while [ "$(jobs -rp | wc -l)" -ge "$MAXJOBS" ]; do sleep 2; done
    run_one "$pid" "$cond" "$panel" "$1" "$2" "$3" &
  done
done < "$JOBS"
wait

python3 - "$OUT/reviews" "$JOBS" <<'PY'
import os, sys
root, jobs = sys.argv[1:3]
have, holes = 0, []
for line in open(jobs):
    pid, cond, panel = line.strip().split("|")
    for s in ("R1", "R2", "R3", "R4", "R5"):
        f = f"{root}/{pid}/{cond}/{panel}/{s}.json"
        if os.path.exists(f) and os.path.getsize(f) > 2:
            have += 1
        else:
            holes.append(f"{pid}/{cond}/{panel}/{s}")
print(f"complete: {have} reviews, {len(holes)} holes" + (f" -> {holes[:6]}" if holes else ""))
PY
log "=== N1b drift pass done ==="
log "next: paired_noise.py --with-drift5"

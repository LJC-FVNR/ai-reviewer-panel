#!/usr/bin/env bash
# run_n0.sh — N0: the vendor-diverse cursor8 panel on the 16 accepted ICLR-2026 papers.
# 16 papers x 2 panels x 8 slots = 256 reviews. It is the run the grade-scale, aggregation and
# roster-transfer results read.
#
# WHY THIS IS A LIKE-FOR-LIKE CONTRAST, and what would silently destroy it:
#   same papers    the exact de-identified manuscript.txt the 5-model calibration consumed
#   same prompt    reviewer_prompt_iclr.md, VERBATIM. It is roster-agnostic (its "panel of 12"
#                  is metrics, not reviewers), so it needs no edit -- and must not get one. If the
#                  8-slot run used cursor_panel's own template, the 2-vendor vs 6-vendor comparison
#                  would be confounded by prompt and the whole point of N0 would be lost.
#   same metrics   verified identical 12 channels in both panel definitions.
#   only the roster differs: 5 slots / 2 vendors  ->  8 slots / 6 vendors.
#
# N0 IS A CALIBRATION RUN. cursor8's composite must be z-scored against cursor8's OWN mu/sd; the
# 5-model calibration_params_portable.json is NOT valid for it. That is the same error class as
# borrowing a noise band from another panel (see yardsticks.py), so the fit runs here, not later.
#
# Gate: --gate-mode like_type_set. All 16 papers are accepted ICLR-2026 main-conference papers, so
# the set is homogeneous and the full-set median IS the like-for-like bar -- by design, not as a
# fallback from a genre cluster (which is an NMI-mixture concept and does not apply here).
#
# Resumable: a paper whose last slot of the last panel already parsed is skipped, so this can be
# re-run after an interruption without re-spending reviews.
#
# Usage: run_n0.sh [--panels 2] [--paper-jobs 3] [--timeout 1800] [--papers N]
set -uo pipefail
export PATH="/path/to/workspace/.local/bin:$PATH"

WS="/path/to/workspace"
CP="$WS/paper_direction_72/cursor_panel"
CAL="$WS/paper_direction_98_calibration"
PROMPT="$CAL/ICLR/reviewer_prompt_iclr.md"
OUT="$WS/ai_native_academia/n0_cursor8_iclr"
MODELS="$CP/panel_models.json"

PANELS=2; PAPER_JOBS=3; TMO=1800; NPAPERS=0
while [ $# -gt 0 ]; do case "$1" in
  --panels)     PANELS="$2"; shift 2;;
  --paper-jobs) PAPER_JOBS="$2"; shift 2;;
  --timeout)    TMO="$2"; shift 2;;
  --papers)     NPAPERS="$2"; shift 2;;
  -h|--help)    sed -n '1,26p' "$0"; exit 0;;
  *) echo "unknown arg $1" >&2; exit 2;;
esac; done

[ -s "$PROMPT" ] || { echo "ERROR: ICLR prompt missing: $PROMPT" >&2; exit 2; }
mkdir -p "$OUT/reviews" "$OUT/inputs"
LOG="$OUT/n0.log"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG" >&2; }

# --- Stage inputs in the layout run_cursor_panel.sh expects --------------------------------------
# Symlinks, not copies: the reviewed bytes must be provably the same bytes the 5-model run used.
# A copy could drift; a symlink cannot. Fail loudly on any paper without a de-identified text
# rather than quietly calibrating on 15.
IDS=()
for d in "$CAL"/deid/build_*; do
  id="$(basename "$d" | sed 's/^build_//')"
  src="$d/manuscript.txt"
  if [ ! -s "$src" ]; then
    log "FATAL: no de-identified manuscript.txt for $id — refusing to calibrate on a partial set"
    exit 2
  fi
  mkdir -p "$OUT/inputs/$id"
  ln -sfn "$src" "$OUT/inputs/$id/manuscript_extracted.txt"
  IDS+=("$id")
done
NALL=${#IDS[@]}
if [ "$NPAPERS" -gt 0 ] && [ "$NPAPERS" -lt "$NALL" ]; then
  IDS=("${IDS[@]:0:$NPAPERS}")
  log "NOTE: --papers $NPAPERS => SUBSET of $NPAPERS/$NALL. A subset gate has a wider CI; do not"
  log "      report a subset run as N0."
fi
N=${#IDS[@]}
log "N0 start: $N papers x $PANELS panels x 8 slots = $((N*PANELS*8)) reviews (paper_jobs=$PAPER_JOBS)"

# --- Preflight once for the whole run ------------------------------------------------------------
# A retired model id must fail here, not punch a hole in 256 reviews. Verified once, then skipped
# per paper: 16 redundant preflights would be 16 wasted API calls.
if ! bash "$CP/verify_models.sh" "$MODELS" >"$OUT/model_verification.txt" 2>&1; then
  log "FATAL: model preflight failed — see $OUT/model_verification.txt"
  cat "$OUT/model_verification.txt" >&2
  exit 2
fi
log "preflight PASS: all 8 slots resolvable ($(date -u +%FT%TZ))"
export CURSOR_PANEL_SKIP_PREFLIGHT=1

LAST_SLOT="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['panel'][-1]['slot'])" "$MODELS")"

# --- Review each paper ---------------------------------------------------------------------------
running=0; launched=0; skipped=0
for id in "${IDS[@]}"; do
  rdir="$OUT/reviews/$id"
  if [ -s "$rdir/panel$PANELS/$LAST_SLOT.json" ]; then
    skipped=$((skipped+1)); continue
  fi
  log "  [run ] $id"
  ( bash "$CP/run_cursor_panel.sh" \
        --manuscript "$OUT/inputs/$id/manuscript_extracted.txt" \
        --template "$PROMPT" \
        --models "$MODELS" \
        --out "$rdir" --panels "$PANELS" --label "$id" --jobs 8 --timeout "$TMO" \
        >"$rdir.log" 2>&1 \
    || echo "[$(date +%H:%M:%S)]   WARN: $id had parse/contamination warnings (see $rdir.log)" >>"$LOG" ) &
  launched=$((launched+1))
  running=$((running+1))
  if [ "$running" -ge "$PAPER_JOBS" ]; then wait -n 2>/dev/null || true; running=$((running-1)); fi
done
wait
log "all panels finished (launched=$launched skipped=$skipped)"

# --- Completeness before fitting -----------------------------------------------------------------
# Fitting mu/sd on a matrix with holes silently biases every channel it touches, so count first.
python3 - "$OUT/reviews" "$MODELS" "$PANELS" <<'PY' | tee -a "$LOG"
import glob, json, os, sys
root, models, panels = sys.argv[1], sys.argv[2], int(sys.argv[3])
slots = [s["slot"] for s in json.load(open(models))["panel"]]
papers = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, "*")) if os.path.isdir(p))
have = miss = 0
holes = []
for p in papers:
    for k in range(1, panels + 1):
        for s in slots:
            f = os.path.join(root, p, f"panel{k}", f"{s}.json")
            if os.path.exists(f) and os.path.getsize(f) > 2:
                have += 1
            else:
                miss += 1
                holes.append(f"{p}/panel{k}/{s}")
print(f"completeness: {have}/{have+miss} reviews parsed ({len(papers)} papers x {panels} panels x {len(slots)} slots)")
if holes:
    print(f"HOLES ({len(holes)}): " + ", ".join(holes[:25]) + (" ..." if len(holes) > 25 else ""))
PY

# --- Fit cursor8's own mu/sd + gate --------------------------------------------------------------
python3 "$CP/fit_calibration.py" \
    --reviews-root "$OUT/reviews" --models "$MODELS" --panels "$PANELS" \
    --gate-mode like_type_set \
    --out-params "$OUT/calibration_params_cursor8_iclr.json" \
    --out-report "$OUT/calibration_report.md" 2>&1 | tee -a "$LOG" || {
  log "ERROR: calibration fit failed"; exit 2; }

# --- Correct the provenance the shared fitter stamps from its own project -------------------------
# fit_calibration.py lives in paper_direction_72 and hardcodes that project's venue (NMI) and prompt
# template name. Left alone, those two fields ship inside the one artifact a reader checks a composite
# against, and they say the parameters were fitted on the wrong corpus with the wrong prompt. mu, sd, the
# gate and the composites are the fitter's own output and are not touched; only the labels are, and by
# script rather than by hand so the file stays derived.
python3 - "$OUT/calibration_params_cursor8_iclr.json" "$PROMPT" <<'PY' | tee -a "$LOG"
import hashlib, json, os, sys
path, prompt = sys.argv[1], sys.argv[2]
d = json.load(open(path))
name = os.path.basename(prompt)
d["venue"] = "ICLR 2026 (accepted)"
d["prompt_template"] = name
d["prompt_sha256"] = hashlib.sha256(open(prompt, "rb").read()).hexdigest()
d["note"] = d["note"].replace("reviewer_prompt_template_v2.md", name)
d["provenance_corrected"] = (
    "venue and prompt_template rewritten by run_n0.sh; the shared fitter stamps paper_direction_72's "
    "venue and prompt. mu, sd, gate and per_paper_composite are the fitter's unmodified output.")
json.dump(d, open(path, "w"), indent=2)
print(f"provenance: venue={d['venue']!r} prompt={name} sha256={d['prompt_sha256'][:16]}")
PY

log "N0 done. params: $OUT/calibration_params_cursor8_iclr.json"
log "Next: yardsticks on THIS panel, then the §3 grade row and §4 vendor-width variance row."

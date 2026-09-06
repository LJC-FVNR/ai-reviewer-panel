#!/usr/bin/env python3
"""Derive PIA's two yardsticks from the corpus and panel that PIA actually uses.

PIA's pass criterion is "a semantics-preserving transform must not move the score more than
re-running the same panel does, nor more than the gap between adjacent papers". Two bands are available
off the shelf, 0.110 z and 0.106 z, and neither serves: 0.110 is the **cursor8 8-model panel's**
noise measured on the **NMI** reference set (paper_direction_72/cursor_panel/README.md, the
`lead_exceeds_noise` discussion), and no computation for 0.106 exists on disk at all. Neither
band belongs to the 5-model panel or to ICLR, which is what the elasticity arm runs on. A ruler
borrowed from a different panel on a different corpus is not a ruler.

Both are recomputable for free, because every paper in the ICLR corpora already carries two
independent panels over identical text:

  test-retest   |panel1 - panel2| on the same manuscript. Same text, same slots, different draw,
                so the spread is the instrument's own irreducible noise. Reported as the median
                and as the sd of the signed difference.
  adjacent gap  median difference between consecutive papers once the reference set is sorted by
                composite. This is "one rank position" in score units -- the unit a venue would
                feel, and the unit rank displacement is measured in.

Run with METRIC unset to use the composite; the composite is what the criterion is stated on.
"""
import glob
import json
import os
import statistics as st
import sys

CAL = "/path/to/workspace/paper_direction_98_calibration"
CALIB = json.load(open(f"{CAL}/ICLR/calibration_params_portable.json"))
MU, SD, METRICS = CALIB["mu"], CALIB["sd"], CALIB["metrics"]
SLOTS = ["R1", "R2", "R3", "R4", "R5"]


def panels(rev_dir):
    """-> list of per-panel mean z over all (slot, metric) channels present."""
    out = []
    for pdir in sorted(glob.glob(os.path.join(rev_dir, "panel*"))):
        zs = []
        for slot in SLOTS:
            f = os.path.join(pdir, f"{slot}.json")
            if not os.path.exists(f) or os.path.getsize(f) < 2:
                continue
            try:
                m = json.load(open(f)).get("metrics", {})
            except Exception:
                continue
            for metric in METRICS:
                key = f"{slot}|{metric}"
                if metric in m and key in MU and SD.get(key):
                    zs.append((m[metric]["score"] - MU[key]) / SD[key])
        if zs:
            out.append(st.mean(zs))
    return out


def report(label, roots):
    diffs, comps = [], []
    for d in sorted(roots):
        p = panels(d)
        if len(p) >= 2:
            diffs.append(p[1] - p[0])
        if p:
            comps.append(st.mean(p))
    if not diffs:
        print(f"{label}: no two-panel papers found")
        return None
    ad = sorted(abs(x) for x in diffs)
    s = sorted(comps)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    r = dict(n_papers=len(comps), n_pairs=len(diffs),
             retest_median_abs=st.median(ad), retest_mean_abs=st.mean(ad),
             retest_sd_signed=st.pstdev(diffs), retest_p90_abs=ad[int(0.9 * (len(ad) - 1))],
             adjacent_median=st.median(gaps) if gaps else None,
             adjacent_mean=st.mean(gaps) if gaps else None,
             spread=s[-1] - s[0])
    print(f"\n{label}  (n={r['n_papers']} papers, {r['n_pairs']} panel pairs)")
    print(f"  test-retest |panel1-panel2|: median {r['retest_median_abs']:.4f} z   "
          f"mean {r['retest_mean_abs']:.4f}   p90 {r['retest_p90_abs']:.4f}   "
          f"sd(signed) {r['retest_sd_signed']:.4f}")
    print(f"  adjacent-paper gap:          median {r['adjacent_median']:.4f} z   "
          f"mean {r['adjacent_mean']:.4f}   (full spread {r['spread']:.4f})")
    return r


out = {}
out["iclr_accepted_16"] = report(
    "ICLR-2026 accepted 16, 5-model panel  [the PIA reference field]",
    glob.glob(f"{CAL}/reviews/*"))
out["iclr_rejected_32"] = report(
    "ICLR-2026 rejected 32, 5-model panel  [wider range, for contrast]",
    glob.glob("reviews/*") if os.path.isdir("reviews") else
    glob.glob("/path/to/workspace/ai_native_academia/reject_arm/reviews/*"))

a = out["iclr_accepted_16"]
print(f"""
{'='*78}
PIA criterion, restated on the corpus and panel PIA uses
  test-retest band  = {a['retest_median_abs']:.3f} z   (was quoted as 0.110, which is the
                      cursor8 panel's noise on NMI -- a different panel and a different corpus)
  one rank position = {a['adjacent_median']:.3f} z   (was quoted as 0.106, with no computation on disk)
A transform passes if mean |dcomposite| stays under both, AND >=90% of papers keep their grade.
Quote these two numbers with the panel and corpus attached, every time.""")
json.dump(out, open("yardsticks.json", "w"), indent=1, default=float)
print("\nwrote yardsticks.json")

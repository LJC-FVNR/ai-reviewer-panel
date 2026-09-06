#!/usr/bin/env python3
"""Reliability of one reviewer versus reliability of a panel mean, measured on ICLR.

§4 needs "single reviewers are unreliable, panel means are not", because that is the mechanism behind
the aggregation null: widening the roster buys reliability, which is not validity. The numbers an early
draft carried for this sentence -- pairwise inter-reviewer Spearman 0.43/0.52/0.54, panel-mean test-retest
0.79/0.82/0.92, reviewer-mean spread up to 2.25 points -- appear in no ICLR artifact on disk, and three
values per statistic point at a corpus this study no longer uses.
Standing rule: every number is recomputed from the corpus at write-up. So this recomputes them.

Two quantities, both per population, both on the composite the ranking claim is stated on:

  inter-slot agreement   Spearman between two SLOTS' orderings of the same papers, over all 10 pairs.
                         How much two reviewers agree is a ceiling on what one reviewer can tell you.
  panel-mean retest      Spearman between panel1's ordering and panel2's, plus mean |Delta| in z.
                         Same text, same slots, different draw: the panel MEAN's own reliability.

The comparison only means something if both are computed on the same papers with the same metric, so
both run off one loader. Reported for the composite (12 metrics, z-standardised per slot+metric, which
is what §5's rho is computed on) and again for raw `overall_recommendation` (the human-legible channel,
which is what the variance decomposition uses) -- if the two disagree, say so rather than picking one.

RESULT, and it inverts the sentence it was written to support. On ICLR the slots agree with each other
STRONGLY: inter-slot Spearman median +0.89 / +0.89 / +0.87 on the three rejected populations and +0.71 on
the accepted 16, with panel-mean retest +0.93 to +0.96. "Single reviewers are unreliable" is false here.
That makes the aggregation null (panel - mean solo = +0.043, CI through zero) a sharper finding rather
than a weaker one: averaging measurements that already correlate at +0.89 cannot recover much, because
what they share is most of what they carry. High agreement plus no validity gain means the slots share
whatever they are responding to -- and §6 identifies part of what that is.

WHICH METRIC FOR WHICH CLAIM, because mixing them produces a false zero. `slot_mean_spread` is exactly
0.0000 for the accepted 16 on the composite, and that is an artifact, not a finding: the composite is
z-scored per (slot, metric) against mu/sd fitted ON those 16 papers, so every slot's mean is 0 there by
construction. Leniency is precisely what the z-scoring removes. So quote **ordering agreement from the
composite** and **leniency/spread from raw `overall_recommendation`**, and never the composite's slot
spread on the calibration set.

Reads the frozen calibration params; never refits. Writes reliability.json.
"""
from __future__ import annotations

import glob
import itertools
import json
import os
import statistics as st

AN = os.path.dirname(os.path.abspath(__file__))
CAL = "/path/to/workspace/paper_direction_98_calibration"
CALIB = json.load(open(f"{CAL}/ICLR/calibration_params_portable.json"))
MU, SD, METRICS = CALIB["mu"], CALIB["sd"], CALIB["metrics"]
SLOTS = ["R1", "R2", "R3", "R4", "R5"]

POPS = [
    ("ICLR rejected, all 32 (heterogeneous)", sorted(glob.glob(f"{AN}/reject_arm/reviews/*_*"))),
    (".. low-rated 16 only", sorted(glob.glob(f"{AN}/reject_arm/reviews/low_*"))),
    (".. high-rated 16 only", sorted(glob.glob(f"{AN}/reject_arm/reviews/high_*"))),
    ("ICLR accepted 16 (homogeneous)", sorted(glob.glob(f"{CAL}/reviews/*"))),
]


def spearman(xs, ys):
    """Spearman rho with midranks, so tied grades do not silently become an ordering."""
    n = len(xs)
    if n < 3:
        return None

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def cell(f, mode):
    """One review file -> a scalar. `mode` picks the composite or the raw overall channel."""
    try:
        m = json.load(open(f)).get("metrics", {})
    except Exception:
        return None
    slot = os.path.basename(f)[:-5]
    if mode == "overall":
        v = m.get("overall_recommendation")
        return v["score"] if v else None
    zs = [(m[k]["score"] - MU[f"{slot}|{k}"]) / SD[f"{slot}|{k}"]
          for k in METRICS if k in m and SD.get(f"{slot}|{k}")]
    return st.mean(zs) if zs else None


def load(roots, mode):
    """-> {paper: {panel: {slot: value}}}, only papers with >=2 panels."""
    out = {}
    for d in roots:
        pid, panels = os.path.basename(d), {}
        for pdir in sorted(glob.glob(os.path.join(d, "panel*"))):
            vals = {}
            for s in SLOTS:
                f = os.path.join(pdir, f"{s}.json")
                if os.path.exists(f) and os.path.getsize(f) > 1:
                    v = cell(f, mode)
                    if v is not None:
                        vals[s] = v
            if vals:
                panels[os.path.basename(pdir)] = vals
        if len(panels) >= 2:
            out[pid] = panels
    return out


def report(label, roots, mode):
    data = load(roots, mode)
    papers = sorted(data)
    if len(papers) < 3:
        return None

    # --- inter-slot: average each slot over its panels first, so slot noise is not panel noise ---
    per_slot = {s: [] for s in SLOTS}
    keep = []
    for p in papers:
        vals = {s: [pan[s] for pan in data[p].values() if s in pan] for s in SLOTS}
        if all(vals[s] for s in SLOTS):
            keep.append(p)
            for s in SLOTS:
                per_slot[s].append(st.mean(vals[s]))
    pair = {}
    for a, b in itertools.combinations(SLOTS, 2):
        r = spearman(per_slot[a], per_slot[b])
        if r is not None:
            pair[f"{a}-{b}"] = round(r, 4)
    pv = sorted(pair.values())

    # --- panel-mean retest: panel1's ordering vs panel2's, on papers carrying both ---
    p1, p2 = [], []
    for p in papers:
        pans = sorted(data[p])
        a, b = data[p][pans[0]], data[p][pans[1]]
        if a and b:
            p1.append(st.mean(a.values()))
            p2.append(st.mean(b.values()))
    retest = spearman(p1, p2)
    absd = [abs(x - y) for x, y in zip(p1, p2)]

    r = dict(n_papers=len(keep), n_retest_pairs=len(p1),
             inter_slot_median=round(st.median(pv), 4), inter_slot_min=round(pv[0], 4),
             inter_slot_max=round(pv[-1], 4), inter_slot_pairs=pair,
             panel_retest_rho=round(retest, 4) if retest is not None else None,
             panel_retest_mean_abs=round(st.mean(absd), 4),
             panel_retest_median_abs=round(st.median(absd), 4),
             slot_mean_spread=round(max(st.mean(per_slot[s]) for s in SLOTS)
                                    - min(st.mean(per_slot[s]) for s in SLOTS), 4))
    print(f"\n{label}   [{mode}]  ({r['n_papers']} papers, {r['n_retest_pairs']} panel pairs)")
    print(f"  inter-slot Spearman over 10 pairs: median {r['inter_slot_median']:+.3f}  "
          f"min {r['inter_slot_min']:+.3f}  max {r['inter_slot_max']:+.3f}")
    print(f"  panel-MEAN retest Spearman:        {r['panel_retest_rho']:+.3f}   "
          f"mean |delta| {r['panel_retest_mean_abs']:.4f}  median {r['panel_retest_median_abs']:.4f}")
    print(f"  slot-mean spread:                  {r['slot_mean_spread']:.4f}")
    return r


def main():
    out = {}
    for mode in ("composite", "overall"):
        print(f"\n{'=' * 88}\n{mode.upper()}\n{'=' * 88}")
        out[mode] = {}
        for label, roots in POPS:
            r = report(label, roots, mode)
            if r:
                out[mode][label] = r
    json.dump(out, open(f"{AN}/reliability.json", "w"), indent=1)
    print(f"\nwrote {AN}/reliability.json")

    print("\nThe §4 sentence. Ordering agreement from the composite, leniency spread from `overall`:")
    for label in [p[0] for p in POPS]:
        c, o = out["composite"].get(label), out["overall"].get(label)
        if c and o:
            print(f"  {label:42s} one reviewer {c['inter_slot_median']:+.2f}  "
                  f"panel mean {c['panel_retest_rho']:+.2f}  "
                  f"leniency spread {o['slot_mean_spread']:.2f} pts")
    z = out["composite"].get("ICLR accepted 16 (homogeneous)", {}).get("slot_mean_spread")
    if z is not None and abs(z) > 1e-9:
        print(f"\nNOTE: composite slot spread on the calibration set is {z}, expected 0.0. Either the "
              "calibration params no longer come from these 16 papers or a slot is missing metrics; "
              "check before quoting any composite-based leniency number.")
    else:
        print("\nComposite slot spread on the calibration set is 0 by construction, as expected -- "
              "z-scoring removes leniency. Do not quote it as a finding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

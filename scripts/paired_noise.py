#!/usr/bin/env python3
"""Is the transform effect larger than the instrument's own movement ON THE SAME PAPER?

Section 6 compares two aggregates: a median |dcomposite| of 0.260 z against a re-run band of 0.160 z, the
band being a median over sixteen papers. That comparison is unpaired, and N2c showed why that matters --
per-paper transform deltas span 2.2x to 3.4x the band and are not ordered by anything, so a ratio of two
medians can be carried by a subset. The paired question is the one a reader actually has: paper by paper,
does the edit move the score further than re-running the panel on the untouched paper does?

Nothing here is a new review. Every contrast below is a difference of two INDEPENDENT single-panel means, so
treatment and noise are the same kind of quantity and directly comparable: if the transform did nothing,
E|V - B| equals E|B1 - B2| exactly.

THE COUNT IS NOT A COIN FLIP, and reading it as one is how this analysis first came out backwards. Four
exchangeable panel composites can be split into two pairs three ways, and the split that puts the two extremes
together always has the largest within-pair distance -- so under H0 the across-pair mean exceeds the
within-pair mean on only about a third of papers, not half. Against 0.5, five of eight looks like nothing;
against the simulated null rate of 0.333 it is p = 0.047. So the verdict here is the permutation p on the
median paired difference, and the win count is printed with the null rate beside it or not at all.

  five-model   treat  = mean of the four |v_j - b_k| over the two variant and two baseline panels
               noise  = mean of |b1 - b2| and |v1 - v2|, the two re-runs of identical text available
  eight-slot   treat  = |v - d|, variant against the drift control, BOTH in the variant session, so a
                        between-session offset cancels in the contrast rather than being corrected for
               noise  = |b1 - b2|, the two baseline panels, also same-session
               cross  = |v - mean(b)| against |d - mean(b)|, the cross-session form: treatment against the
                        one condition whose true effect is known to be zero

  python3 paired_noise.py [--bundle release/aina2026_agent_reviewers] [--json paired_noise.json]

Exit status is 0 whatever the answer. This is a check that can come out against the paper.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import statistics as st

AN = os.path.dirname(os.path.abspath(__file__))
VARIANTS = [("T1_endmatter", "T1"), ("T2_concede", "T2"), ("T3_lengthen", "T3")]


def load(pat):
    return {f: json.load(open(f)) for f in sorted(glob.glob(pat)) if os.path.getsize(f) > 2}


def zmean(review, slot, mu, sd, metrics):
    z = [(review["metrics"][m]["score"] - mu[f"{slot}|{m}"]) / sd[f"{slot}|{m}"]
         for m in metrics if m in review.get("metrics", {}) and sd.get(f"{slot}|{m}")]
    return st.mean(z) if z else None


def panels(root, mu, sd, metrics, pat, levels=1):
    """-> {unit: {panel: composite}}; unit is the paper, or "<paper>/<variant>" when levels=2."""
    out: dict[str, dict[str, list]] = {}
    for f, r in load(f"{root}/{'/'.join(['*'] * levels)}/panel*/{pat}").items():
        parts = f.split("/")
        v = zmean(r, os.path.basename(f)[:2], mu, sd, metrics)
        if v is not None:
            out.setdefault("/".join(parts[-(levels + 2):-2]), {}).setdefault(parts[-2], []).append(v)
    return {u: {k: st.mean(v) for k, v in d.items()} for u, d in out.items()}


def sign_flip_p(rows):
    """Exact one-sided p over all 2^n label swaps, for a contrast whose two halves are exchangeable under H0.

    This is valid exactly where swapping the two conditions is a relabelling and nothing else. It holds for the
    eight-slot CROSS-SESSION contrast and only there: the drift panel and the variant panel are the same
    roster reading texts of the same length distribution in the same session against the same baselines, so
    under "the edit changes nothing" |v - b| and |d - b| are draws from one distribution and the sign of their
    difference is a coin. Statistic is the count of papers where treatment wins, so this is also the sign test
    -- but here p = 0.5 is derived from the design rather than assumed.
    """
    n, wins = len(rows), sum(1 for _, t, s in rows if t > s)
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n


def pairing_p(quads, iters=200000, seed=11):
    """Permutation p for the five-model contrast, where a coin flip is NOT the null.

    The statistic compares distances ACROSS the baseline/variant split against distances WITHIN it, over four
    panel composites per paper. Under H0 those four are exchangeable, so the observed split is one of the three
    ways to pair four points -- and the three are not equally likely to look large: the pairing that puts the
    two extremes together always has the biggest within-sum. So P(across > within) under H0 is not 0.5, and a
    sign test against 0.5 would read a design artefact as an effect. Instead: re-split each paper's four panels
    at random, recompute, and count how often the null median paired difference reaches the observed one.

    This assumes the four panels are exchangeable, which the arm cannot verify -- variants were scored in a
    later session, and only the eight-slot roster has the drift control that measures what that is worth.
    """
    rng = random.Random(seed)
    obs = st.median(across - within for across, within in (stat(q) for q in quads))
    hit, wins = 0, 0
    for _ in range(iters):
        d = []
        for q in quads:
            v = list(q)
            rng.shuffle(v)
            across, within = stat(v)
            d.append(across - within)
        hit += st.median(d) >= obs
        wins += sum(x > 0 for x in d)
    # The null win RATE, reported because the win COUNT is the number a reader will reach for and it is not a
    # coin: four exchangeable panels split three ways, and the split that pairs the two extremes always has the
    # largest within-distance. Against this rate, not against 50%, is how "5 of 8" has to be read.
    return (hit + 1) / (iters + 1), obs, wins / (iters * len(quads))


def stat(four):
    """-> (mean cross-pair distance, mean within-pair distance) for [v1, v2, b1, b2]."""
    v, b = four[:2], four[2:]
    return (st.mean(abs(x - y) for x in v for y in b), st.mean([abs(v[0] - v[1]), abs(b[0] - b[1])]))


def report(title, rows, note="", p=None, plabel=""):
    """rows: [(paper, treat, noise)] -> printed table plus the paired verdict."""
    n = len(rows)
    wins = sum(1 for _, t, s in rows if t > s)
    diffs = [t - s for _, t, s in rows]
    print(f"\n{title}")
    if note:
        print(f"  {note}")
    print(f"  {'paper':<14}{'treat':>9}{'noise':>9}{'diff':>9}")
    for pa, t, s in sorted(rows, key=lambda r: r[2] - r[1]):
        print(f"  {pa[:14]:<14}{t:>9.3f}{s:>9.3f}{t - s:>+9.3f}")
    print(f"  larger on {wins} of {n} papers" + (f", {plabel} p = {p:.3f} (one-sided)" if p is not None else ""))
    print(f"  median treat {st.median(t for _, t, _ in rows):.3f} z, median noise "
          f"{st.median(s for _, _, s in rows):.3f} z, median paired difference {st.median(diffs):+.3f} z")
    return {"n": n, "wins": wins, "p_one_sided": None if p is None else round(p, 4), "null": plabel,
            "median_treat": round(st.median(t for _, t, _ in rows), 4),
            "median_noise": round(st.median(s for _, _, s in rows), 4),
            "median_paired_diff": round(st.median(diffs), 4),
            "per_paper": {pa: [round(t, 4), round(s, 4)] for pa, t, s in rows}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=f"{AN}/release/aina2026_agent_reviewers")
    ap.add_argument("--json", default=f"{AN}/paired_noise.json")
    a = ap.parse_args()
    B = a.bundle
    out: dict[str, dict] = {}

    cal = json.load(open(f"{B}/calibration/calibration_params_portable.json"))
    mu, sd, metrics = cal["mu"], cal["sd"], cal["metrics"]
    base5 = panels(f"{B}/reviews/accepted", mu, sd, metrics, "R?.json")
    var5 = panels(f"{B}/reviews/transform", mu, sd, metrics, "R?.json", levels=2)

    print("=" * 78)
    print("FIVE-MODEL PANEL -- every contrast is one panel against another, treatment or not")
    for variant, short in VARIANTS:
        rows, quads = [], []
        for unit, vp in sorted(var5.items()):
            paper, v = unit.split("/")
            if v != variant or paper not in base5 or len(vp) < 2 or len(base5[paper]) < 2:
                continue
            b, w = list(base5[paper].values()), list(vp.values())
            quads.append(w + b)
            treat, noise = stat(w + b)
            rows.append((paper, treat, noise))
        p, _, null_rate = pairing_p(quads, iters=50000)
        d = report(f"{short}: transform against the same paper's own re-run", rows,
                   "treat = mean|variant panel - baseline panel| over 4 pairings; noise = mean of the two "
                   "re-runs",
                   p, "re-split permutation")
        print(f"  a win rate of {null_rate:.3f} is what H0 predicts, so the count is not read against 0.5")
        d["null_win_rate"] = round(null_rate, 4)
        out[f"5model_{short}"] = d

    c8 = json.load(open(f"{B}/calibration/calibration_params_cursor8.json"))
    mu8, sd8, met8 = c8["mu"], c8["sd"], c8["metrics"]
    base8 = panels(f"{B}/reviews/vendor_panel", mu8, sd8, met8, "C?.json")
    var8 = panels(f"{B}/reviews/vendor_transform", mu8, sd8, met8, "C?.json", levels=2)
    drift8 = panels(f"{B}/reviews/vendor_drift", mu8, sd8, met8, "C?.json")

    print("\n" + "=" * 78)
    print("EIGHT-SLOT ROSTER -- the drift control makes the treatment contrast same-session")
    for variant, short in VARIANTS:
        same, cross = [], []
        for unit, vp in sorted(var8.items()):
            paper, v = unit.split("/")
            if v != variant or paper not in drift8 or paper not in base8 or len(base8[paper]) < 2:
                continue
            b = list(base8[paper].values())
            d = st.mean(drift8[paper].values())
            w = st.mean(vp.values())
            same.append((paper, abs(w - d), abs(b[0] - b[1])))
            cross.append((paper, abs(w - st.mean(b)), abs(d - st.mean(b))))
        out[f"8slot_{short}_same_session"] = report(
            f"{short}: variant vs drift control, both in the variant session", same,
            "treat = |variant - drift|, session offset cancelled; noise = |baseline panel1 - panel2| -- the two "
            "sides cross different session boundaries, so no exact null: descriptive")
        out[f"8slot_{short}_cross_session"] = report(
            f"{short}: variant vs the condition whose true effect is zero", cross,
            "treat = |variant - baseline mean|; noise = |drift - baseline mean|, the same session boundary",
            sign_flip_p(cross), "exact label-swap")

    json.dump(out, open(a.json, "w"), indent=1)
    print(f"\nwrote {os.path.relpath(a.json, AN)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

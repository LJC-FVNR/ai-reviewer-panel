#!/usr/bin/env python3
"""N1b: what the five-model arm's own drift control says about section 6.

Section 6's five-model deltas difference a variant against a baseline scored during calibration, days
earlier. Any level shift in either provider between those sessions sits inside every delta and looks exactly
like the treatment -- and all three transforms came out negative, which is the shape a common negative offset
would have. N1b re-scores the byte-identical baselines and the variants in the same shuffled queue, so every
contrast it reports has both of its halves inside one session:

  drift        = N1b baseline composite - calibration baseline composite. Measured on this roster and this
                 gateway, not borrowed from the eight-slot roster on a different one.
  band_now     = median |N1b panel_i - N1b panel_j|, this roster's re-run band measured in the session the
                 variants were scored in. A per-paper band is |difference of two noisy panel means|, so it is
                 mostly noise rather than a property of the paper and it regresses hard to the mean. Whether
                 it differs from calibration's is therefore a question to be tested rather than read off the
                 two medians, and the paired test is printed for exactly that reason. The paper's yardstick is
                 calibration's band; a smaller number here is not a competing one.
  clean delta  = N1b variant - mean(N1b baselines from the same pass), both inside one session. This is
                 section 6's effect with NO session boundary anywhere in the contrast. If it agrees with the
                 cross-session delta, drift was not carrying section 6. If it collapses, it was.
  paired test  = |variant - baseline anchor| against |other baseline - anchor|. Under "the edit changes
                 nothing" the variant panel and the other baseline panel are the same estimator on
                 same-scoring text, so swapping their labels is a relabelling and the 2^n label swap is
                 EXACT, with none of the exchangeability assumption paired_noise.py had to make. The anchor
                 is the lower-numbered panel because run_n1b.sh declared it before the queue ran. Exact is
                 not the same as powerful: the noise term is one heavy-tailed |panel - panel| gap per paper,
                 and switching the anchor can move p a long way without touching a review. Both anchors are
                 printed and the arm's verdict rests on the signed clean delta, not on this.

TWO PASSES, and which pass a variant was scored in decides which baselines it is differenced against. The
first pass carries the presentation variants and two baseline panels; the second carries T2 and two more.
T2 is here because section 6 divides one arm's cost by another's, and a ratio whose numerator has no session
boundary and whose denominator has one is not a ratio of two costs. Differencing T2 against the first pass's
baselines would have put the pass boundary back inside it, so it takes its own pass's panels, and the two
passes' baselines are compared directly to price that boundary rather than assume it away.

  python3 n1b_analyze.py [--n1b n1b_drift_5model] [--bundle release/...] [--json n1b_results.json]

Exit status is 0 whatever the answer. This arm can come out against the paper.
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import statistics as st

AN = os.path.dirname(os.path.abspath(__file__))
# (condition, short name, the two baseline panels scored in the same pass as that condition). A variant
# differenced against the other pass's baselines would carry the pass boundary inside the contrast, which is
# the boundary this whole arm exists to remove. A variant whose panels are absent is skipped, so this file
# reports pass one alone before pass two has run.
VARIANTS = [("T1_endmatter", "T1", ("panel1", "panel2")),
            ("T3_lengthen", "T3", ("panel1", "panel2")),
            ("T2_concede", "T2", ("panel3", "panel4"))]


def load(pat):
    return {f: json.load(open(f)) for f in sorted(glob.glob(pat)) if os.path.getsize(f) > 2}


def zmean(review, slot, mu, sd, metrics):
    z = [(review["metrics"][m]["score"] - mu[f"{slot}|{m}"]) / sd[f"{slot}|{m}"]
         for m in metrics if m in review.get("metrics", {}) and sd.get(f"{slot}|{m}")]
    return st.mean(z) if z else None


def panels(root, mu, sd, metrics, levels=1):
    """-> {unit: {panel: composite}}; unit is "<paper>" or "<paper>/<condition>" when levels=2."""
    out: dict[str, dict[str, list]] = {}
    for f, r in load(f"{root}/{'/'.join(['*'] * levels)}/panel*/R?.json").items():
        parts = f.split("/")
        v = zmean(r, os.path.basename(f)[:2], mu, sd, metrics)
        if v is not None:
            out.setdefault("/".join(parts[-(levels + 2):-2]), {}).setdefault(parts[-2], []).append(v)
    return {u: {k: st.mean(v) for k, v in d.items()} for u, d in out.items()}


def sign_p(pos, n):
    """Exact two-sided binomial sign-test p for `pos` positives out of n, against 0.5."""
    from math import comb
    tail = sum(comb(n, k) for k in range(min(pos, n - pos) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def boot(xs, fn=st.median, iters=20000, seed=7):
    """Percentile bootstrap 95% CI, the same form section 6 quotes its deltas in.

    Of the MEDIAN by default, because the median is the statistic every interval in this file is printed
    beside and reproduce.py bootstraps for the same rows. Bootstrapping the mean and printing the interval
    next to a median is how an interval comes to belong to a number nobody quoted.
    """
    import random
    rng, n, s = random.Random(seed), len(xs), []
    for _ in range(iters):
        s.append(fn([xs[rng.randrange(n)] for _ in range(n)]))
    s.sort()
    return s[int(0.025 * iters)], s[int(0.975 * iters)]


def swap_p(rows):
    """Exact one-sided p over all 2^n swaps of the two same-session labels. rows: [(paper, treat, noise)]."""
    d = [t - s for _, t, s in rows]
    obs = st.median(d)
    hits = sum(st.median(x) >= obs for x in itertools.product(*[(v, -v) for v in d]))
    return hits / 2 ** len(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n1b", default=f"{AN}/n1b_drift_5model")
    ap.add_argument("--bundle", default=f"{AN}/release/aina2026_agent_reviewers")
    ap.add_argument("--json", default=f"{AN}/n1b_results.json")
    a = ap.parse_args()
    out: dict[str, object] = {}

    cal = json.load(open(f"{a.bundle}/calibration/calibration_params_portable.json"))
    mu, sd, metrics = cal["mu"], cal["sd"], cal["metrics"]
    old_b = panels(f"{a.bundle}/reviews/accepted", mu, sd, metrics)
    old_v = panels(f"{a.bundle}/reviews/transform", mu, sd, metrics, levels=2)
    new = panels(f"{a.n1b}/reviews", mu, sd, metrics, levels=2)

    papers = sorted({u.split("/")[0] for u in new})
    have = lambda p, k: k in new.get(f"{p}/baseline", {})
    print("=" * 88)
    print(f"DRIFT: byte-identical baselines, calibration session vs the N1b session, five-model panel, "
          f"{len(papers)} papers")
    print(f"  {'paper':<12}{'calib':>9}{'n1b p1':>9}{'n1b p2':>9}{'n1b mean':>10}{'drift':>9}{'|p1-p2|':>9}")
    drift, band = [], []
    for p in papers:
        nb = new[f"{p}/baseline"]
        p1, p2 = nb["panel1"], nb["panel2"]
        n, o = st.mean([p1, p2]), st.mean(old_b[p].values())
        drift.append(n - o)
        band.append(abs(p1 - p2))
        print(f"  {p:<12}{o:>9.3f}{p1:>9.3f}{p2:>9.3f}{n:>10.3f}{n - o:>+9.3f}{abs(p1 - p2):>9.3f}")
    npos = sum(x > 0 for x in drift)
    lo, hi = boot(drift)
    print(f"  drift: median {st.median(drift):+.3f} z, mean {st.mean(drift):+.3f} z, 95% CI "
          f"[{lo:+.3f}, {hi:+.3f}], {npos} of {len(drift)} positive, sign test p = "
          f"{sign_p(npos, len(drift)):.3f}")
    out["drift"] = {"per_paper": dict(zip(papers, (round(x, 4) for x in drift))),
                    "median": round(st.median(drift), 4), "mean": round(st.mean(drift), 4),
                    "ci95": [round(lo, 4), round(hi, 4)],
                    "n_positive": npos, "n": len(drift), "sign_p": round(sign_p(npos, len(drift)), 4)}

    # Is the panel more repeatable now than in calibration? Almost certainly not: this is the check that
    # stops 0.025 z from being quoted as a new yardstick beside the paper's 0.160 z.
    calb = {p: abs(old_b[p]["panel1"] - old_b[p]["panel2"]) for p in papers if len(old_b[p]) >= 2}
    smaller = sum(band[i] < calb[p] for i, p in enumerate(papers) if p in calb)
    nb = len(calb)
    print(f"  band, same estimator both sessions: calibration median {st.median(calb.values()):.3f} z on "
          f"these {nb} papers, N1b median {st.median(band):.3f} z")
    print(f"    smaller now on {smaller} of {nb}, sign test p = {sign_p(smaller, nb):.3f}. A per-paper band "
          f"is a heavy-tailed noise quantity that regresses to the mean, so the paired test above")
    print(f"    and not the gap between the two medians is what says whether the instrument's "
          f"repeatability changed; calibration's band remains the paper's yardstick.")
    out["band_same_session"] = {"median": round(st.median(band), 4),
                                "per_paper": dict(zip(papers, (round(x, 4) for x in band))),
                                "calibration_median_same_papers": round(st.median(calb.values()), 4),
                                "n_smaller_now": smaller, "n": nb,
                                "sign_p": round(sign_p(smaller, nb), 4)}

    for cond, short, (pa, pb) in VARIANTS:
        if not any(have(p, pa) and have(p, pb) for p in papers):
            print(f"\n{short}: no baseline {pa}/{pb} on disk -- that pass has not been scored, skipping")
            continue
        print("\n" + "=" * 88)
        print(f"{short}: the effect with no session boundary in the contrast, and with one "
              f"(baselines {pa}, {pb})")
        print(f"  {'paper':<12}{'clean d':>9}{'x-sess d':>10}{'treat':>9}{'noise':>9}{'diff':>9}")
        clean, cross, rows, rows2, own_band, kept = [], [], [], [], [], []
        for p in papers:
            v = new.get(f"{p}/{cond}", {}).get("panel1")
            if v is None or not (have(p, pa) and have(p, pb)):
                continue
            nb = new[f"{p}/baseline"]
            b1, b2 = nb[pa], nb[pb]
            cd = v - st.mean([b1, b2])
            # The cross-session column is section 6's own form, read from the bundle. A paper the bundle does
            # not carry yet leaves the cell empty rather than poisoning the column's median with a NaN.
            xd = (st.mean(old_v[f"{p}/{cond}"].values()) - st.mean(old_b[p].values())
                  if f"{p}/{cond}" in old_v and p in old_b else None)
            clean.append(cd)
            if xd is not None:
                cross.append(xd)
            own_band.append(abs(b2 - b1))
            rows.append((p, abs(v - b1), abs(b2 - b1)))
            rows2.append((p, abs(v - b2), abs(b1 - b2)))
            kept.append(p)
            print(f"  {p:<12}{cd:>+9.3f}{'' if xd is None else f'{xd:+10.3f}':>10}"
                  f"{rows[-1][1]:>9.3f}{rows[-1][2]:>9.3f}{rows[-1][1] - rows[-1][2]:>+9.3f}")
        n = len(clean)
        nneg = sum(x < 0 for x in clean)
        p1, p2 = swap_p(rows), swap_p(rows2)
        clo, chi = boot(clean)
        print(f"  clean same-session delta: median {st.median(clean):+.3f} z, mean {st.mean(clean):+.3f} z, "
              f"95% CI [{clo:+.3f}, {chi:+.3f}], {nneg} of {n} negative, sign test p = "
              f"{sign_p(n - nneg, n):.3f}")
        print(f"  same-session re-run band in this pass: median {st.median(own_band):.3f} z, so the clean "
              f"median is {abs(st.median(clean)) / st.median(own_band):.2f}x this pass's own band")
        if cross:
            print(f"  cross-session delta (the paper's form): median {st.median(cross):+.3f} z, "
                  f"mean {st.mean(cross):+.3f} z, over the {len(cross)} papers the bundle carries")
        else:
            print(f"  cross-session delta: the bundle carries no {short} cell for these papers")
        print(f"  paired: treat larger on {sum(1 for _, t, s in rows if t > s)} of {n}, "
              f"median paired difference {st.median(t - s for _, t, s in rows):+.3f} z, "
              f"exact label-swap p = {p1:.4f}")
        print(f"          panel2 as anchor: p = {p2:.4f} (the arbitrary half of the anchor choice)")
        out[short] = {
            "baseline_panels": [pa, pb],
            "band_this_pass": round(st.median(own_band), 4),
            "clean_same_session": {"per_paper": dict(zip(kept, (round(x, 4) for x in clean))),
                                   "median": round(st.median(clean), 4), "mean": round(st.mean(clean), 4),
                                   "ci95": [round(clo, 4), round(chi, 4)],
                                   "n_negative": nneg, "n": n, "sign_p": round(sign_p(n - nneg, n), 4)},
            "cross_session_median": round(st.median(cross), 4) if cross else None,
            "cross_session_n": len(cross),
            "paired": {"anchor": pa, "wins": sum(1 for _, t, s in rows if t > s), "n": n,
                       "median_paired_diff": round(st.median(t - s for _, t, s in rows), 4),
                       "exact_swap_p": round(p1, 4), "exact_swap_p_anchor2": round(p2, 4),
                       "per_paper": {p: [round(t, 4), round(s, 4)] for p, t, s in rows}}}

    # The pass boundary itself. Two baseline panels in each pass on byte-identical text, so this contrast is
    # the same shape as the drift contrast above with the calibration session replaced by pass one. If it is
    # small against the band, splitting the arm across two passes cost nothing; if it is not, T2's number is
    # not comparable to T1's and the appendix has to say so.
    both = [p for p in papers if all(have(p, k) for k in ("panel1", "panel2", "panel3", "panel4"))]
    if both:
        print("\n" + "=" * 88)
        print(f"THE PASS BOUNDARY: byte-identical baselines, pass 1 vs pass 2, {len(both)} papers")
        step = [st.mean([new[f"{p}/baseline"]["panel3"], new[f"{p}/baseline"]["panel4"]])
                - st.mean([new[f"{p}/baseline"]["panel1"], new[f"{p}/baseline"]["panel2"]]) for p in both]
        b12 = [abs(new[f"{p}/baseline"]["panel1"] - new[f"{p}/baseline"]["panel2"]) for p in both]
        b34 = [abs(new[f"{p}/baseline"]["panel3"] - new[f"{p}/baseline"]["panel4"]) for p in both]
        npos = sum(x > 0 for x in step)
        lo, hi = boot(step, fn=st.median)
        print(f"  offset: median {st.median(step):+.3f} z, mean {st.mean(step):+.3f} z, 95% CI "
              f"[{lo:+.3f}, {hi:+.3f}], {npos} of {len(step)} positive, sign test p = "
              f"{sign_p(npos, len(step)):.3f}")
        print(f"  against the band: pass 1 median {st.median(b12):.3f} z, pass 2 median "
              f"{st.median(b34):.3f} z")
        out["pass_boundary"] = {"median": round(st.median(step), 4), "mean": round(st.mean(step), 4),
                               "ci95": [round(lo, 4), round(hi, 4)], "n_positive": npos, "n": len(step),
                               "sign_p": round(sign_p(npos, len(step)), 4),
                               "band_pass1": round(st.median(b12), 4),
                               "band_pass2": round(st.median(b34), 4),
                               "per_paper": dict(zip(both, (round(x, 4) for x in step)))}

    json.dump(out, open(a.json, "w"), indent=1)
    print(f"\nwrote {os.path.relpath(a.json, AN)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

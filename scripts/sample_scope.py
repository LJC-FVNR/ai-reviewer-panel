#!/usr/bin/env python3
"""What the corpus can resolve, arm by arm: the answer to "forty-eight papers, is that enough?".

A reader who counts samples counts papers, and the count they land on is 48 -- sixteen accepted and thirty-two
declined. That count is worth answering with arithmetic rather than with a defence, and the arithmetic has two
parts, because the number of papers and the number of reviews buy different things.

  papers      every headline delta is estimated over papers, so the precision of an arm is sd/sqrt(n_papers)
              and the effect it can resolve is a multiple of that. This is the term a bigger draw buys down.
  reviews     re-scoring the same paper buys down only the panel's own noise inside each paper's delta. Once
              that term is small next to the between-paper term, more reviews per paper buy nothing the
              criterion cares about, which is why this study spent its budget on papers instead.

So this prints, for each transform arm and for the same arm at sixteen papers: the median it reports, the width
of that median's measured interval, the effect it resolves at two-sided 5% and 80% power, and that effect as a
share of the pre-registered re-run band the criterion compares against. An arm resolving an effect the size of
its own band is the wrong instrument for an invariance claim, because the case that matters is a true effect of
half a band: small enough that a reader would call it small and large enough that a venue would still see it.

The precision is taken from an interval on the median rather than from sd/sqrt(n), because the median is what
every arm row prints; the last two columns show the mean's figure, which is narrower for all three arms and so
would credit the paper with precision its own rows do not have.

That interval is the exact distribution-free one -- a pair of order statistics whose coverage is a binomial
tail -- and not the percentile bootstrap the arm rows print. The bootstrap is the obvious choice and it is the
wrong one here: with forty-seven papers a resampled median lands on a handful of neighbouring order statistics,
so the half-width jumps between a few discrete values, and re-running that bootstrap under another seed moved
this figure by 0.007 z, a twelfth of the band. A number that depends on a seed is not a number a reader can
check. The order-statistic interval needs no seed and no distributional assumption, its coverage is at least
the nominal 95 per cent, and it is the wider of the two on every arm here, so it is also the conservative
reading of the row the paper prints.

The deltas read here are the per-paper column the release ships, and that column is rounded to four places.
A half-width is a difference of two order statistics, so it inherits both of their roundings, and recomputing
the same interval from the reviews moves it in the fifth place -- enough to move a fourth printed digit. The
appendix table therefore stops at three, which is where this file and a recomputation from the reviews agree.

Two terms sit inside each arm's spread and only one of them is bought down by re-scoring: the panel's own noise
inside a paper's delta, and the real difference between papers. This does not recompute that split, because the
arm already reports it as a ratio against its own re-run null with an interval on it, measured on the arm's own
papers. A second decomposition here would need a panel sigma of its own, the nearest one to hand is measured on
sixteen accepted papers rather than on the arm's forty-eight, and pricing one arm's variance with another
population's noise is how one paper comes to carry two answers to one question. What is quoted below is
therefore the arm's precision, and the heterogeneity question stays where its interval is.

Nothing here sets a threshold or recommends an expansion. It reports what the corpus resolves; the criterion
the arms are judged against was fixed before any of them were scored and is not restated here.

    python3 sample_scope.py         # -> sample_scope.json, and a report on stdout
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
from statistics import NormalDist

Z975 = 1.959963985                 # two-sided 5%
Z80 = 0.841621234                  # 80% power
Z = Z975 + Z80
HERE = os.path.dirname(os.path.abspath(__file__))
WAS_16 = 16                        # the arm size before the expansion, kept as the comparison this answers


def beside(name):
    """-> the first existing path called `name` in this script's directory, its parent, or the staged tree.

    This script ships inside the bundle it counts, where it sits one level below the tree and beside no
    working directory at all. Resolving each input by looking is what lets the same file run in both places;
    hard-coding the working layout would ship a script that cannot recount the count it printed.
    """
    for p in (f"{HERE}/release/aina2026_agent_reviewers/{name}", f"{HERE}/{name}", f"{HERE}/../{name}",
              f"{HERE}/release/aina2026_agent_reviewers/data/{name}", f"{HERE}/../data/{name}"):
        if os.path.exists(p):
            return p
    raise SystemExit(f"cannot find {name} beside {HERE}")


STAGE = os.path.dirname(beside("reviews"))
POOLED = json.load(open(beside("pooled_analysis.json"), encoding="utf-8"))
BAND = POOLED["band_rerun_preregistered"]


def mde(sd, n):
    """The effect a mean over n papers resolves at two-sided 5% and 80% power, given a per-paper spread."""
    return Z * sd / math.sqrt(n)


def sign_interval(vals):
    """-> (k, coverage, lo, hi, half) for the exact distribution-free interval on the median of `vals`.

    The order statistics x_(k) and x_(n+1-k) bracket the population median with probability
    1 - 2*P(Bin(n, 1/2) < k), which is arithmetic on the sample size alone: no distributional assumption, no
    fitted spread, no seed. `k` is the largest index whose two-sided binomial tail still fits inside 5%, so the
    interval is the tightest one of this family that holds its nominal coverage, and its actual coverage is
    returned with it because a discrete family overshoots and the conversion below has to divide by the
    deviate the coverage really corresponds to.
    """
    xs = sorted(vals)
    n = len(xs)
    k = max(j for j in range(1, n // 2 + 1)
            if 2 * sum(math.comb(n, i) for i in range(j)) / 2 ** n <= 0.05)
    coverage = 1 - 2 * sum(math.comb(n, i) for i in range(k)) / 2 ** n
    lo, hi = xs[k - 1], xs[n - k]
    return k, coverage, lo, hi, (hi - lo) / 2


def mde_from_interval(half, coverage, n, at_n):
    """The effect the arm's own estimator resolves, taken from a measured interval on that estimator.

    Every arm row in the paper is a median, not a mean, because the per-paper deltas are not symmetric. Pricing
    precision with sd/sqrt(n) would therefore price an estimator the paper does not print, and for these arms
    it prices it optimistically: the normal interval on T1's mean is a fifth narrower than either measured
    interval on its median. So a measured half-interval is the unit. It is converted to a detectable effect by
    the ratio of two normal deviates -- the sum of the 5% and 80% deviates over the deviate the interval's own
    coverage corresponds to -- and moved between paper counts by the root-n rate an interval on a median
    follows for large n. Nothing here is fitted, and nothing here is resampled.
    """
    return half * (Z / NormalDist().inv_cdf((1 + coverage) / 2)) * math.sqrt(n / at_n)


def reviews():
    """-> {arm: (papers, reviews, reviews per paper)}, on the arms the release is organised into.

    The arm names, the glob and the empty-file rule are the ones reproduce.py counts the corpus with, and the
    tree is the staged release rather than the working directory, for the same reason: a count of reviews is a
    property of what shipped. A hand-rolled second definition of "a review" is how two numbers in one paper
    come to disagree, so the total these arms sum to is asserted against the count the paper already prints,
    read out of the reproduction table rather than typed here.
    """
    ARMS = ("accepted", "rejected", "transform", "transform_rejected", "drift_5model", "dayrep_5model",
            "vendor_panel", "vendor_transform", "vendor_drift")
    out = {}
    for arm in ARMS:
        files = [f for f in glob.glob(f"{STAGE}/reviews/{arm}/**/[RC]?.json", recursive=True)
                 if os.path.getsize(f) > 2]
        if not files:
            continue
        papers = {os.path.relpath(f, f"{STAGE}/reviews/{arm}").split("/")[0] for f in files}
        out[arm] = (len(papers), len(files), len(files) / len(papers))
    return out


def main():
    rep = {"band": BAND, "power": {"alpha_two_sided": 0.05, "power": 0.80, "z_sum": Z}}

    print("reviews behind each arm of the release, and how many per paper")
    rv = reviews()
    for label, (papers, n, per) in rv.items():
        print(f"   {label:<22} {papers:>3} papers  {n:>5} reviews  {per:>5.1f} per paper")
    total = sum(v[1] for v in rv.values())
    printed = int(re.search(r'"corpus: total reviews",\s*(\d+)',
                            open(beside("reproduce.py"), encoding="utf-8").read()).group(1))
    assert total == printed, f"this counts {total} reviews, the paper prints {printed}"
    print(f"   {'all arms':<22} {'':>3}         {total:>5} reviews, the count the paper states")
    rep["reviews"] = {k: dict(papers=v[0], reviews=v[1], per_paper=v[2]) for k, v in rv.items()}
    rep["reviews_total"] = total

    print(f"\nwhat each arm resolves, against the pre-registered band of {BAND:.3f} z")
    print(f"   {'arm':<14} {'n':>3} {'median':>8} {'df half':>8} {'cover':>6} {'resolves':>9} {'of band':>8}   "
          f"{'at n=16':>8} {'of band':>8}   {'boot half':>9} {'(sd form)':>9} {'at 16':>7}")
    arms = {}
    for name, block in POOLED["arms"].items():
        pooled = block["pooled"]
        n, sd = pooled["n"], pooled["sd"]
        lo, hi = pooled["ci95"]
        boot_half = (hi - lo) / 2
        vals = list(block["per_paper"].values())
        assert len(vals) == n, f"{name}: {len(vals)} per-paper deltas against the row's n of {n}"
        k, coverage, df_lo, df_hi, half = sign_interval(vals)
        row = dict(n=n, sd=sd, median=pooled["median"], ci95=[lo, hi], ci_half=boot_half,
                   df_k=k, df_coverage=coverage, df_ci=[df_lo, df_hi], df_half=half,
                   mde=mde_from_interval(half, coverage, n, n),
                   mde_over_band=mde_from_interval(half, coverage, n, n) / BAND,
                   mde_at_16=mde_from_interval(half, coverage, n, WAS_16),
                   mde_at_16_over_band=mde_from_interval(half, coverage, n, WAS_16) / BAND,
                   mde_sd_form=mde(sd, n), mde_sd_form_at_16=mde(sd, WAS_16))
        arms[name] = row
        print(f"   {name:<14} {n:>3} {row['median']:>+8.4f} {half:>8.4f} {coverage:>6.3f} {row['mde']:>9.4f} "
              f"{row['mde_over_band']:>7.2f}x   {row['mde_at_16']:>8.4f} {row['mde_at_16_over_band']:>7.2f}x   "
              f"{boot_half:>9.4f} {row['mde_sd_form']:>9.4f} {row['mde_sd_form_at_16']:>7.4f}")
    print("   the last two columns price the mean instead, which the paper does not report: for every arm the\n"
          "   mean's normal interval is the narrower one, so quoting it would claim precision the printed row\n"
          "   does not have. The column before them is the printed row's own bootstrap half-width, which the\n"
          "   distribution-free interval used here is never narrower than.")
    # Both stated above, so checked here rather than trusted. If any arm's mean were the less precise estimator
    # the comparison sentence would be false and the conservative column would be the other one; and if the
    # seed-free interval came out narrower than the bootstrap one the arm row prints, this would be quoting
    # precision that row does not carry, which is the defect the estimator was changed to avoid.
    assert all(r["mde_sd_form"] < r["mde"] for r in arms.values()), \
        "the mean is not the narrower estimator on every arm; the printed comparison is wrong"
    assert all(r["df_half"] >= r["ci_half"] for r in arms.values()), \
        "an arm's distribution-free interval is narrower than the bootstrap interval its row prints"

    # The same question for the arm as a whole rather than transform by transform: the smallest effect any of
    # the three would have resolved, which is the number a reader counting papers is really asking about.
    worst = max(arms, key=lambda k: arms[k]["mde"])
    best = min(arms, key=lambda k: arms[k]["mde"])
    print(f"\n   across the three arms the design resolves {arms[best]['mde']:.4f} to {arms[worst]['mde']:.4f} z, "
          f"{arms[best]['mde_over_band']:.2f}x to {arms[worst]['mde_over_band']:.2f}x the band; the same arms at "
          f"{WAS_16} papers\n   resolved {arms[best]['mde_at_16']:.4f} to {arms[worst]['mde_at_16']:.4f} z, "
          f"{arms[best]['mde_at_16_over_band']:.2f}x to {arms[worst]['mde_at_16_over_band']:.2f}x, so the arm was "
          f"then a test that could only see an effect\n   the size of the band it is compared against.")
    rep["arms"] = arms
    rep["summary"] = dict(mde_min=arms[best]["mde"], mde_max=arms[worst]["mde"],
                          over_band_min=arms[best]["mde_over_band"], over_band_max=arms[worst]["mde_over_band"],
                          mde_at_16_min=arms[best]["mde_at_16"], mde_at_16_max=arms[worst]["mde_at_16"],
                          at_16_over_band_min=arms[best]["mde_at_16_over_band"],
                          at_16_over_band_max=arms[worst]["mde_at_16_over_band"])

    json.dump(rep, open(f"{HERE}/sample_scope.json", "w", encoding="utf-8"), indent=1, default=float)
    print("\nwrote sample_scope.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

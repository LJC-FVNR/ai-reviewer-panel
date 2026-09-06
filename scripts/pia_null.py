#!/usr/bin/env python3
"""The presentation-invariance result against a matched null, at composite, group and channel resolution.

WHAT THE PAPER DOES NOW. analyse_n1.py's pre-registered criterion compares median|delta| against the
test-retest band, median|panel1 - panel2| = 0.160 z on the five-model roster. F4 then counts channels whose
median delta is at or below -0.14, which is 5 for T1 and 3 for T3. Neither number is a significance test,
and the second uses a threshold that appears nowhere else in the paper. Meanwhile the body table's own
bootstrap interval for T1's composite delta is [-0.324, +0.127] -- it crosses zero -- so the paper's
strongest quantitative claim is carried by a magnitude comparison while its one interval estimate declines
to exclude no effect, in bold, next to the word "fails".

TWO THINGS WRONG WITH THE COMPARISON, both fixable without a new run.

  Scale. On the five-model roster delta is a difference of two-panel means: variant (2 panels) minus
  baseline (2 panels), so with per-panel noise sigma its variance is sigma^2/2 + sigma^2/2 = sigma^2. The
  band is a difference of two single panels, variance 2 sigma^2. The band is therefore sqrt(2) too wide for
  the statistic it judges, and the criterion is conservative by that factor -- 0.160 should be 0.113. Left
  uncorrected in the criterion, which already fires; corrected here, where the null is the point. The
  eight-slot roster scored one variant panel against a two-panel baseline, so its factor is sqrt(3)/2, and
  it is derived from the panel counts rather than typed.

  Centre. A bootstrap of the re-run differences keeps whatever offset each channel's pool happens to carry,
  and with 8 or 16 papers those offsets are large: statistical_soundness's treated-8 pool sits at +0.078,
  which alone turns a -0.078 delta into p = 0.010. The panel labels are arbitrary -- the two calibration
  panels ran interleaved in one 40-minute window on byte-identical prompts, verified -- so every sign
  assignment to a re-run difference is equally likely, and randomising the signs is what generates the
  null. It is centred at zero by construction.

THE TEST. For an axis (a set of channels), per paper: mean z over (slot, channel) within a panel, then
over panels, exactly as analyse_n1.py's composite() does it.

  delta      median over the treated papers of variant - baseline
  null       the same median with the treatment removed: the untouched papers' (panel2 - panel1), scaled to
             the treated statistic's variance, signs randomised
  p signs    the sign assignments of the treated papers' own differences. Every one of them where the arm is
             small enough to enumerate -- 2^8 = 256 on eight papers, 2^16 = 65536 on sixteen -- and 200,000
             drawn where it is not, which is every arm past ENUM_MAX papers, the forty-seven-paper ones
             included. So the resolution is one over whichever count applied, and a printed bound means no
             assignment out of that many reached the observed value. `exact_assignments` in the JSON is that
             count, not 2^n, and is what the printed floor is taken from
  p pooled   k of the untouched pool without replacement x random signs, always 200,000 draws. Answers "any
             k papers"

One-sided, since every transform is predicted to lower a score. A channel or group is reported as moved
only if both p-values clear 0.05, because the sign null is severely discrete on a small arm and the pooled
null assumes papers are exchangeable; disagreement between them is a reason to claim nothing. Per-channel counts
also get Benjamini-Hochberg over the nine non-allotted channels, which is the family such a count is drawn
from.

THREE RESOLUTIONS, because the claim does not live at the channel level. "This edit moved channels it
cannot legitimately move" is a statement about the non-allotted group, and a group of nine channels has
about a third of one channel's noise. Testing the nine separately and counting the survivors throws that
away, and makes the headline a function of where the threshold sits.

  python3 pia_null.py            # -> pia_null.json, both rosters
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics as st
import sys

import numpy as np

WS = "/path/to/workspace"
AN = f"{WS}/ai_native_academia"
CAL = f"{WS}/paper_direction_98_calibration"
DRAWS = 200_000
SEED = 20260831
FIXED = -0.14                      # F4's threshold, quoted only to report what it counts
from readings import panel_day

# T1 and T3 are the presentation-invariance transforms (analyse_n1.PIA_VALID). T2 is here for the opposite
# reason: it rewrites claim strength, so it is the arm where the panel is SUPPOSED to move, and its
# allotment is the eleven channels a claim-softening edit is licensed to reach. Reading it beside the other
# two is what separates "the panel is noisy" from "the panel reads the wrong things": a transform that
# withdraws a significance claim and a transform that joins two sentences cannot both be invisible, and
# they cannot both be large, without saying something about which one the instrument is tracking.
TRANSFORMS = ("T1_endmatter", "T3_lengthen", "T2_concede")
PIA = ("T1_endmatter", "T3_lengthen")            # analyse_n1.PIA_VALID, in a fixed order

# Both rosters, because the second one is the paper's answer to "would vendor diversity fix this" and a
# significance test on one roster beside a ratio-to-band on the other invites exactly that question again.
# var_panels is the number of panels the variant arm got; it sets the variance the null is scaled to, and
# the two rosters differ (5-model scored two variant panels, 8-slot one).
ROSTERS = {
    "5model": dict(params=f"{CAL}/ICLR/calibration_params_portable.json",
                   base=f"{CAL}/reviews/*", slots="R?.json", var_panels=2,
                   var=lambda p, t: f"{AN}/n1_pia_5model/reviews/{p}__{t}"),
    # The same roster and the same ruler, differenced against baseline panels scored on the SAME DAY as
    # the variant panel rather than against the calibration sitting two months earlier. Untouched text
    # reads 0.213 z lower on 2026-09-01 than on 2026-08-31, which is larger than either transform's
    # composite effect, so the contrast that holds the day fixed is the one that measures the transform.
    # It costs precision to buy that: one variant panel instead of two, and the variance match follows.
    "5model_matched": dict(params=f"{CAL}/ICLR/calibration_params_portable.json",
                           base=f"{AN}/n1b_drift_5model/reviews/*/baseline", slots="R?.json",
                           var_panels=1, day_matched=True,
                           pid=lambda d: os.path.basename(os.path.dirname(d)),
                           var_panel_names=("panel1",),
                           var=lambda p, t: f"{AN}/n1b_drift_5model/reviews/{p}/{t}"),
    "8slot": dict(params=f"{AN}/n0_cursor8_iclr/calibration_params_cursor8_iclr.json",
                  base=f"{AN}/n0_cursor8_iclr/reviews/*", slots="C?.json", var_panels=1,
                  var=lambda p, t: f"{AN}/n2_pia_cursor8/reviews/{p}/{t}"),
}

# The day-matched contrast over BOTH corpora: sixteen accepted papers and thirty-two rejected ones, 48 in
# all. This exists because sixteen papers can only resolve an effect about as large as the band it is judged
# against -- MDE 0.134 z against a band of 0.160 -- and the between-paper term that dominates the spread
# shrinks with papers and not with re-scoring. Three variant panels on sixteen papers stops at 0.105; one
# variant panel on forty-eight reaches 0.077. The ruler is the accepted arm's for both. Its offsets cancel,
# because they are subtracted from both sides of a within-paper difference; its scales do not cancel, they set
# the unit the delta is reported in. That is the property wanted here: the criterion's band is stated in those
# same units, so a delta from either corpus is compared against the band on one ruler, and neither corpus's own
# spread is allowed to decide how large its own effect looks.
# No `base_panels` here, and none in the matched roster above, on purpose. A day-matched roster chooses its
# baseline panels by the variant's day, and a key that names panel1 and panel2 would be read as the selection
# rule while having no effect on it. That gap is how three scripts in this tree came to report two different
# day-matched medians for the same arm: one of them selected by name and dropped every paper whose first two
# baseline panels fell on the other side of the boundary, which is half the T2 arm. The rule is in
# `matched_axis`, stated once, and nothing outside it may appear to set it.
_MATCHED = dict(var_panel_names=("panel1",))
ROSTERS["5model_pooled"] = dict(
    params=f"{CAL}/ICLR/calibration_params_portable.json", slots="R?.json", var_panels=1,
    day_matched=True,
    sources=[
        dict(base=f"{AN}/n1b_drift_5model/reviews/*/baseline",
             pid=lambda d: os.path.basename(os.path.dirname(d)),
             var=lambda p, t: f"{AN}/n1b_drift_5model/reviews/{p}/{t}", **_MATCHED),
        dict(base=f"{AN}/n1c_reject_5model/reviews/*/baseline",
             pid=lambda d: os.path.basename(os.path.dirname(d)),
             var=lambda p, t: f"{AN}/n1c_reject_5model/reviews/{p}/{t}", **_MATCHED),
    ])

# The rejected corpus on its own, which is the pooled roster's second source read without its first. The
# channel decomposition is the paper's strongest claim -- a presentation edit moving channels it has no
# business reaching -- and a claim that strong should be shown to replicate in a corpus it was not developed
# on rather than only in a pool that contains the corpus it was. `5model_matched` above is the accepted arm
# alone, so the two are a matched pair of single-corpus readings on one ruler.
ROSTERS["5model_rejected"] = dict(
    params=f"{CAL}/ICLR/calibration_params_portable.json", slots="R?.json", var_panels=1,
    day_matched=True, base=f"{AN}/n1c_reject_5model/reviews/*/baseline",
    pid=lambda d: os.path.basename(os.path.dirname(d)),
    var=lambda p, t: f"{AN}/n1c_reject_5model/reviews/{p}/{t}", **_MATCHED)

# The same day-matched five-slot reading as `5model_matched`, cut to the eight papers the eight-slot roster
# has variants for. Without it the table sets a forty-six-paper contrast beside an eight-paper one and the
# difference between them gets read as a difference between two panels; those eight are also the group on
# which figure relocation is expensive, so the confound runs the way that makes the two panels look as though
# they order the presentation arms differently. The list comes from the other roster's own analysis output. It
# is not typed here, because a hand-copied list of papers is one arm re-run away from describing a set that no
# longer exists.
_EIGHT = sorted(json.load(open(f"{AN}/n2_pia_cursor8/n2_analysis.json"))["transforms"]["T1_endmatter"]
                ["per_paper"]) if os.path.exists(f"{AN}/n2_pia_cursor8/n2_analysis.json") else None
if _EIGHT:
    ROSTERS["5model_eight"] = dict(
        params=f"{CAL}/ICLR/calibration_params_portable.json", slots="R?.json", var_panels=1,
        day_matched=True, base=f"{AN}/n1b_drift_5model/reviews/*/baseline",
        pid=lambda d: os.path.basename(os.path.dirname(d)),
        var=lambda p, t: f"{AN}/n1b_drift_5model/reviews/{p}/{t}", only=set(_EIGHT), **_MATCHED)

# Imported, not retyped. The allotment already exists in four places (analyse_n1.LEGITIMATE,
# fig3.LEGIT_T1, fig4.LEGIT, audit_t3_captions.py's prose); they agree today, and a fifth copy here could
# disagree with the figure while both files looked right. Taken from `analyse_n1` rather than from `fig4`
# because that is where it was declared and the figure's copy is a copy -- and because it is the only one
# of the two that carries T2, whose licensed set is needed below.
sys.path.insert(0, AN)
import analyse_n1                                                        # noqa: E402
LEGIT = analyse_n1.LEGITIMATE
import fig4                                                              # noqa: E402
assert {t: LEGIT[t] for t in fig4.LEGIT} == fig4.LEGIT, "the figure's allotment has drifted from the source"


# Panels that were read past because a slot was missing. A set rather than a list because `axis` is called
# once per channel group and would otherwise report the same directory fifteen times.
SKIPPED = set()


def panel_means(rev_dir, cols, mu, sd, slots, panels=None):
    """-> per-panel mean z over (slot, channel in cols), one paper. analyse_n1.composite()'s rule.

    `panels` names the panels to read instead of all of them, and exists because one directory here holds
    panels scored on different days. Reading all four of the drift arm's baseline panels would put a day
    offset inside the baseline of a contrast built to hold the day fixed.

    A PANEL IS ONLY READ WHEN EVERY SLOT CONTRIBUTED. The composite is a mean over slots, so a panel
    missing four of its five reviewers is not a noisier panel, it is one reviewer's opinion carrying a
    panel's weight; its spread is about the square root of five times too wide and it enters the median on
    equal terms with a complete reading. That is not hypothetical. While the rejected arm was still being
    scored, one variant directory held a single review, and the reading built from it was the largest
    positive value in the arm -- large enough on its own to move the paired contrast between the two
    transforms from about -0.24 to +0.02, which is the difference between a claim and no claim.

    The complete slot set is not a constant written here. It is read off the ruler: the calibration
    parameters are keyed `slot|channel`, so the slots the ruler was fitted on are exactly the slots a panel
    scored against it is supposed to have. Five for the five-model roster, eight for the vendor roster, and
    a roster that grows a slot cannot leave this check behind. Incomplete panels are collected in `SKIPPED`
    and printed, because a guard that drops data quietly is worse than the data it dropped.
    """
    out = []
    n_slots = len({k.split("|")[0] for k in mu})
    names = [os.path.join(rev_dir, x) for x in panels] if panels else \
        sorted(glob.glob(os.path.join(rev_dir, "panel[0-9]")))
    for pdir in names:
        if not os.path.isdir(pdir):
            continue
        zs, seen = [], set()
        for f in sorted(glob.glob(os.path.join(pdir, slots))):
            slot = os.path.basename(f)[:-5]
            try:
                rev = json.load(open(f))
            except Exception:
                continue
            for m in cols:
                key, md = f"{slot}|{m}", rev.get("metrics", {}).get(m)
                if key in mu and sd.get(key) and md and isinstance(md.get("score"), (int, float)):
                    zs.append((md["score"] - mu[key]) / sd[key])
                    seen.add(slot)
        if zs and len(seen) == n_slots:
            out.append(st.mean(zs))
        elif zs:
            SKIPPED.add((pdir, len(seen), n_slots))
    return out


def baseline_by_panel(d, cols, mu, sd, slots):
    """-> {panel name: (mean z, day)} for one paper's baseline directory.

    Needed because which baseline panels belong in a day-matched contrast is a property of the paper, not
    of the roster: the drift arm scored some papers' first two baseline panels on one day and some on the
    next, and its later passes added two more panels on a single day. A roster that names panel1 and panel2
    for everyone therefore differences a third of the arm across the boundary it was built to avoid.
    """
    out = {}
    for pdir in sorted(glob.glob(os.path.join(d, "panel[0-9]"))):
        nm = os.path.basename(pdir)
        z = panel_means(d, cols, mu, sd, slots, [nm])
        if z:
            out[nm] = (z[0], panel_day(pdir))
    return out


def matched_axis(cols, R, mu, sd, srcs, scale, transforms=None):
    """axis() for a day-matched roster: every paper differenced against TWO baseline panels of its own day.

    Two, not every same-day panel that happens to exist. Taking all of them would average four panels for
    the papers whose baselines fell on the day the later passes ran and two for the rest, which is unbiased
    and still wrong: the per-paper deltas become a mixture of two estimators with different noise, and the
    rejected corpus only ever has two baseline panels, so an accepted-versus-rejected comparison would
    partly be a comparison of baseline precision. Two per paper, in panel order, in both corpora.
    """
    bp, src_of, rerun = {}, {}, {}
    for S in srcs:
        for d in sorted(glob.glob(S["base"])):
            if not os.path.isdir(d):
                continue
            b = baseline_by_panel(d, cols, mu, sd, R["slots"])
            if b:
                pid = S.get("pid", os.path.basename)(d)
                bp[pid], src_of[pid] = b, S
    # The re-run pair that calibrates the null has to come from the day the delta was measured on. Half the
    # drift arm has baseline panels on two days, because a later pass added two more, so for those papers
    # there are two candidate pairs; taking the earlier one while the delta uses the later one would set the
    # null's width from a day the arm was never treated on. Today the two coincide for every paper and both
    # transforms in scope, so this changes no number. It is written this way so it stays true if a pass is
    # added, if an arm is re-scored, or if a queue drains across midnight.
    TF = transforms or TRANSFORMS
    vday_of = {}
    for pid in bp:
        S, ds = src_of[pid], set()
        for t in TF:
            vd = S["var"](pid, t)
            vnames = list(S.get("var_panel_names") or
                          [os.path.basename(x) for x in sorted(glob.glob(f"{vd}/panel[0-9]"))])
            dy = panel_day(os.path.join(vd, vnames[0])) if vnames else None
            if dy:
                ds.add(dy)
        # One re-run value per paper is only well defined while a paper's treated panels share a day. If they
        # ever do not, the band and the sign null need a day of their own per transform, and this function has
        # to say so rather than pick one of the two.
        assert len(ds) <= 1, (f"{pid}'s variant panels for {sorted(TF)} span {sorted(ds)}; the re-run "
                              f"reference is one value per paper, so ask about one day's transforms at a time")
        vday_of[pid] = ds
    for pid, b in bp.items():
        # The variant's day first; then any day with a pair, which is what an untouched paper gets -- it
        # enters the pooled null and has no variant day to match.
        for dy in sorted(vday_of[pid]) + sorted({dd for _, dd in b.values()}):
            names = [n for n in sorted(b) if b[n][1] == dy]
            if len(names) >= 2:
                rerun[pid] = (b[names[1]][0] - b[names[0]][0]) * scale
                break
    deltas = {}
    for t in TF:
        row = {}
        for pid, b in bp.items():
            S = src_of[pid]
            vd = S["var"](pid, t)
            if not os.path.isdir(vd):
                continue
            vnames = list(S.get("var_panel_names") or
                          [os.path.basename(x) for x in sorted(glob.glob(f"{vd}/panel[0-9]"))])
            z = panel_means(vd, cols, mu, sd, R["slots"], vnames)
            if not z:
                continue
            vday = panel_day(os.path.join(vd, vnames[0]))
            same = [n for n in sorted(b) if b[n][1] == vday][:2]
            if len(same) < 2:
                continue
            row[pid] = st.mean(z) - st.mean(b[n][0] for n in same)
        deltas[t] = row
    return deltas, rerun, scale


def restrict(deltas, rerun, scale, only):
    """-> the same three values with the papers outside `only` dropped, and a check that any were inside.

    An empty result would otherwise read downstream as an arm that has not been scored yet, which is what a
    filter written against a stale id convention produces.
    """
    if only is None:
        return deltas, rerun, scale
    kept = {t: {p: v for p, v in row.items() if p in only} for t, row in deltas.items()}
    have = {p for row in kept.values() for p in row}
    assert have, f"a paper filter of {len(only)} ids matched none of this roster's papers"
    return kept, {p: v for p, v in rerun.items() if p in only}, scale


def axis(cols, R, mu, sd, transforms=None):
    """-> (treated deltas per transform, variance-matched re-run differences) for one set of channels.

    `transforms` narrows the question to some of the arms. It exists because the re-run reference is one
    value per paper, taken from the day the delta was measured on, and that is only well defined while the
    transforms being asked about were scored on the same day as each other. T1 and T3 always were. T2 was
    not, for the papers scored in the earlier sitting -- so T2 is asked about on its own, with its own day,
    rather than being averaged into a reference belonging to a sitting it did not happen in.

    A roster's `only` narrows the PAPERS, which is a different question and is asked for one reason: two
    rosters covering different numbers of papers cannot be compared until one of them is cut down to the
    other's set. It is applied here, after both paths have produced their per-paper dictionaries, so a
    filter cannot end up applying to the day-matched reading and not the plain one. The re-run reference is
    filtered with the deltas, since a null scaled by papers outside the contrast is not this contrast's null.
    """
    # A single-panel difference carries 2 sigma^2. The treated delta carries sigma^2/v + sigma^2/2 for v
    # variant panels against a two-panel baseline, so this is the factor that makes the null the right
    # width -- 1/sqrt(2) for the five-model arm, sqrt(3)/2 for the eight-slot arm.
    scale = math.sqrt((1 / R["var_panels"] + 1 / 2) / 2)
    # A roster may draw on more than one corpus. The sources are kept separate here only so each can name
    # its own extraction tree and its own id convention; every reading is scored with one ruler and enters
    # one pool, because a delta pooled over corpora is still a within-paper difference and the corpus a
    # paper came from is not a term in it.
    srcs = R.get("sources") or [R]
    if R.get("day_matched"):
        return restrict(*matched_axis(cols, R, mu, sd, srcs, scale, transforms), only=R.get("only"))
    TF = transforms or TRANSFORMS
    base, rerun, src_of = {}, {}, {}
    for S in srcs:
        for d in sorted(glob.glob(S["base"])):
            if not os.path.isdir(d):
                continue
            p = panel_means(d, cols, mu, sd, R["slots"], S.get("base_panels"))
            pid = S.get("pid", os.path.basename)(d)
            if p:
                base[pid] = st.mean(p)
                src_of[pid] = S
            if len(p) >= 2:
                rerun[pid] = (p[1] - p[0]) * scale
    deltas = {}
    for t in TF:
        row = {}
        for pid in base:
            S = src_of[pid]
            vd = S["var"](pid, t)
            if not os.path.isdir(vd):
                continue
            p = panel_means(vd, cols, mu, sd, R["slots"], S.get("var_panel_names"))
            if p:
                row[pid] = st.mean(p) - base[pid]
        deltas[t] = row
    return restrict(deltas, rerun, scale, R.get("only"))


ENUM_MAX = 22          # 2^22 sign vectors is the largest enumeration worth holding in memory


def null_exact(pool, rng=None):
    """-> (sorted medians over sign assignments of pool, whether that was an enumeration).

    The arm this enumerates over grew, which is the point of enumerating: at eight papers the floor is
    1/256 and only a unanimous sweep reaches it, and at sixteen it is 1/65536. Past ENUM_MAX papers the
    enumeration stops being affordable and the signs are SAMPLED instead, which is the same null drawn
    rather than listed. Refusing there would have been worse than it looks: `test()` only reports an axis
    as moved when both nulls clear 0.05, so an absent sign null silently turns the moved flag off for
    every axis in the larger arm -- a growing sample would have looked like a vanishing effect.
    """
    a = np.asarray(pool, dtype=float)
    if len(a) <= ENUM_MAX:
        signs = 1 - 2 * ((np.arange(2 ** len(a))[:, None] >> np.arange(len(a))) & 1)
        return np.sort(np.median(a * signs, axis=1)), True
    rng = rng or np.random.default_rng(SEED)
    signs = rng.integers(0, 2, size=(DRAWS, len(a))) * 2 - 1
    return np.sort(np.median(a * signs, axis=1)), False


def null_pooled(pool, k, rng):
    """-> sorted medians over k of len(pool) drawn without replacement, signs randomised."""
    a = np.asarray(pool, dtype=float)
    idx = np.argsort(rng.random((DRAWS, len(a))), axis=1)[:, :k]
    return np.sort(np.median(a[idx] * (rng.integers(0, 2, size=(DRAWS, k)) * 2 - 1), axis=1))


def pval(nulls, v, exact):
    """One-sided share at or below v. The +1 is the Monte Carlo correction, wrong for an enumeration."""
    n = int(np.searchsorted(nulls, v, "right"))
    return float(n / len(nulls)) if exact else float((n + 1) / (len(nulls) + 1))


def pval_two(nulls, v, exact):
    """Two-sided share at least as far from zero as v, in either direction.

    `pval` above tests one tail, downward, and that is the direction the presentation criterion was
    declared in: the claim on file is that the panel PENALISES a presentation edit. Applied to every
    axis of every arm, though, it cannot see an upward move at all -- and one arm here is expected to
    move upward. T2 withdraws a claim of statistical significance and adds a paragraph conceding
    unisolated confounds, so a channel that reads how honestly a paper describes its own evidence
    should go UP, and the arm exists to check that the instrument tracks claim strength at all. With
    only a lower tail, that check reports the arm's honesty channel as one of the quiet ones.

    The null is exactly symmetric about zero, because it is built by randomising the sign of every
    paper's difference and the set of assignments is closed under a global flip. So the far tail needs
    no second null: doubling the nearer tail is the symmetric two-sided p and nothing is re-drawn.

    This is reported beside the one-sided p, never in place of it. The leak family and its
    Benjamini-Hochberg correction stay one-sided and downward, as declared, because a family threshold
    moved after seeing which way a channel went is not a threshold.
    """
    lo = pval(nulls, v, exact)
    hi = (float(len(nulls) - int(np.searchsorted(nulls, v, "left"))) / len(nulls) if exact
          else float(len(nulls) - int(np.searchsorted(nulls, v, "left")) + 1) / (len(nulls) + 1))
    return float(min(1.0, 2 * min(lo, hi)))


def test(name, n_cols, allotted, deltas, rerun, rng):
    d = sorted(deltas.values())
    obs = st.median(d)
    only = [x for p, x in rerun.items() if p in deltas]
    npool = null_pooled(list(rerun.values()), len(d), rng)
    nex, enumerated = null_exact(only, rng) if len(only) == len(d) else (None, None)
    sd = float(npool.std(ddof=0))
    # A discrete re-run pool with a large atom at zero makes the median of a null draw nearly constant, and on
    # a small arm exactly constant. So the sd is not always a usable scale, and dividing by it is how a delta
    # of a tenth of a z comes to be reported as thirty sigma. The share of the pool that is exactly zero is
    # carried out with the result, because it is the condition rather than a symptom of it, and a reader of
    # the JSON should not have to infer it from a small number.
    zero_share = (sum(1 for x in rerun.values() if x == 0) / len(rerun)) if rerun else None
    pp, pe = pval(npool, obs, False), None if nex is None else pval(nex, obs, enumerated)
    p2p = pval_two(npool, obs, False)
    p2e = None if nex is None else pval_two(nex, obs, enumerated)
    return dict(axis=name, n_channels=n_cols, n_papers=len(d), delta=obs, allotted=allotted,
                n_negative=sum(1 for x in d if x < 0), n_positive=sum(1 for x in d if x > 0),
                null_sd=sd, d_over_sd=None if sd == 0 else obs / sd,
                null_point_mass=sd == 0, rerun_zero_share=zero_share, p_pooled=pp, p_exact=pe,
                p_pooled_two=p2p, p_exact_two=p2e,
                sign_null_enumerated=enumerated,
                exact_assignments=None if nex is None else len(nex),
                moved=bool(pp < 0.05 and pe is not None and pe < 0.05),
                # Same conjunction, both tails. Kept apart from `moved` by name as well as by value: the
                # criterion is stated in one direction and this is a description of where the channel went.
                moved_either_way=bool(p2p < 0.05 and p2e is not None and p2e < 0.05),
                leak_fixed=obs <= FIXED, negative=obs < 0)


def row(r):
    # An exact p of zero is "no sign assignment reaches this", a resolution statement and not a probability
    # of zero, so it prints as the floor it actually is.
    pe = ("     n/a" if r["p_exact"] is None else
          f"<{1 / r['exact_assignments']:.4f}" if r["p_exact"] == 0 else f" {r['p_exact']:.4f}")
    ds = "   n/a" if r["d_over_sd"] is None else f"{r['d_over_sd']:+6.2f}"
    return (f"  {r['axis']:24s} {r['delta']:+8.4f} {r['null_sd']:8.4f} {ds:>6s} "
            f"{r['p_pooled']:7.4f} {pe:>8s}  {r['n_papers']:2d}  "
            f"{r['n_negative']}-/{r['n_positive']}+")


HEAD = (f"  {'axis':24s} {'delta':>8s} {'null sd':>8s} {'d/sd':>6s} {'p pool':>7s} {'p signs':>8s}   "
        f"n  sign")


def roster(label, R, res):
    calib = json.load(open(R["params"]))
    mu, sd, metrics = calib["mu"], calib["sd"], calib["metrics"]
    rng = np.random.default_rng(SEED)
    out_r = {"var_panels": R["var_panels"], "transforms": {}}

    # The band is quoted against the presentation-invariance criterion, so it is measured on the days the
    # presentation transforms were scored. T2's own band is printed with T2 below, because its sitting
    # differs for the papers read in the earlier one and one number cannot stand for both.
    _, comp_rerun, scale = axis(metrics, R, mu, sd, transforms=PIA)
    raw = st.median([abs(x) / scale for x in comp_rerun.values()])
    print(f"\n=== {label}: {len(comp_rerun)} untouched papers, {R['var_panels']} variant panel(s)")
    print(f"composite test-retest band, median |panel1-panel2|: {raw:.4f}")
    print(f"  matched to this roster's treated statistic (x{scale:.4f}): {raw * scale:.4f}")
    out_r["band_single_panel"], out_r["band_matched"], out_r["scale"] = raw, raw * scale, scale

    # Does the variant arm reproduce itself as well as the baseline arm does? The variance match assumes
    # one sigma for both arms and nothing else in the repository checks it. Where it can be checked, it
    # does not hold: both five-model variant arms re-run TIGHTER than untouched text, T3 by a factor of
    # four. The transform lowers the instrument's variance along with its mean, which is a result in
    # itself -- and it means a null built from the untouched arm's spread is conservative, the direction to
    # be wrong in. The eight-slot arm has one variant panel, so it cannot be checked there.
    if R["var_panels"] >= 2:
        for t in TRANSFORMS:
            sp = [abs(p[1] - p[0]) for pid in comp_rerun
                  for p in [panel_means(R["var"](pid, t), metrics, mu, sd, R["slots"])] if len(p) >= 2]
            if sp:
                print(f"  same band inside the {t} arm, over its {len(sp)} variant texts: "
                      f"{st.median(sp):.4f}")
                out_r.setdefault("band_variant_arm", {})[t] = st.median(sp)

    for t in TRANSFORMS:
        allot = sorted(LEGIT[t])
        rest = sorted(set(metrics) - set(allot))
        print(f"\n{label} / {t}\n  allotted ({len(allot)}): {', '.join(allot)}")
        if t not in PIA:
            # Its own band, because its sitting is its own. The header's band is measured on the days the
            # presentation transforms were scored, and for the papers read in the earlier sitting this arm
            # was not one of them.
            _, rr, sc = axis(metrics, R, mu, sd, transforms=(t,))
            b = st.median([abs(x) / sc for x in rr.values()])
            print(f"  this arm's own re-run band: {b:.4f} raw, {b * sc:.4f} matched, over {len(rr)} papers")
        print(HEAD)
        out = []
        for name, cols, is_allot in ([("composite (all 12)", metrics, None),
                                      (f"allotted group ({len(allot)})", allot, True),
                                      (f"non-allotted group ({len(rest)})", rest, False)]
                                     + [(m, [m], m in allot) for m in metrics]):
            deltas, rerun, _ = axis(cols, R, mu, sd, transforms=(t,))
            r = test(name, len(cols), is_allot, deltas[t], rerun, rng)
            out.append(r)
            print(row(r))
            if name.startswith("non-allotted"):
                print("  " + "-" * 66)

        # The family is named, not counted. It was `n_channels == 1`, which is true of a single channel and
        # also true of a GROUP axis whose group happens to hold one member -- and T2's non-licensed set holds
        # exactly one, figure quality. So the eight-slot roster reported two leaks out of a family of one: the
        # channel and the group over it are the same test, entered twice. Selecting by membership in the
        # ruler's own metric list cannot collide, because no group label is a metric name.
        chans = [r for r in out if r["axis"] in metrics]
        assert len(chans) == len(metrics), "a per-channel axis is missing or a group label shadowed a metric"
        # Multiplicity over the non-allotted channels only -- the family the leak count is drawn from; the
        # allotted ones are not candidates for it. Each channel enters at the LARGER of its two p-values,
        # since a channel only counts where both nulls agree. Benjamini-Hochberg rather than Bonferroni
        # because they are read off the same papers and are correlated.
        fam = sorted((r for r in chans if not r["allotted"]),
                     key=lambda r: max(r["p_pooled"], r["p_exact"] or 0))
        for r in fam:
            r["p_family"] = max(r["p_pooled"], r["p_exact"] or 0)
            r["p_family_two"] = max(r["p_pooled_two"], r["p_exact_two"] or 0)

        def bh_step(rows, key, flag):
            """Benjamini-Hochberg at q 0.05 over `rows` ranked by `key`, writing `flag` on each survivor.

            Factored out because it now runs twice over the same family, once on the declared one-sided p
            and once two-sided. Running it in one direction for one arm and both for another would let a
            claim be protected by the choice of tail, which is the thing the correction is here to stop.
            """
            ordered = sorted(rows, key=lambda r: r[key])
            k = 0
            for i, r in enumerate(ordered, 1):
                if r[key] <= i * 0.05 / len(ordered):
                    k = i
            for i, r in enumerate(ordered, 1):
                r[flag] = i <= k
            return [r["axis"] for r in ordered if r[flag]]

        bh = bh_step(fam, "p_family", "bh_survives")
        bh2 = bh_step(fam, "p_family_two", "bh_two_survives")
        leaks = sorted(r["axis"] for r in fam if r["moved"])
        grp = next(r for r in out if r["axis"].startswith("non-allotted"))
        print(f"  -> {len(fam)} non-allotted channels, counted as moved: "
              f"{sum(1 for r in fam if r['negative'])} at any negative median, "
              f"{sum(1 for r in fam if r['leak_fixed'])} at {FIXED}, "
              f"{len(leaks)} at p<0.05 both nulls {leaks}, {len(bh)} after BH q=0.05 {bh}")
        print(f"     as a group the {len(fam)} move {grp['delta']:+.4f} = {grp['d_over_sd']:+.2f} null sd,"
              f" p_pool {grp['p_pooled']:.4f} -> {'MOVED' if grp['moved'] else 'not distinguishable'}")
        # Every channel that clears 0.05 on both nulls in EITHER direction, printed for all three arms and
        # not only for the one whose prediction points upward, because a statistic reported where it helps
        # and omitted where it does not is a selection and not a statistic.
        both = [r for r in chans if r["moved_either_way"]]
        print(f"     two-sided, either direction: {len(both)} of {len(chans)} channels -> " +
              ("; ".join(f"{r['axis']} {r['delta']:+.4f} "
                         f"({'down' if r['delta'] < 0 else 'up'}, p {max(r['p_pooled_two'], r['p_exact_two']):.4f}"
                         f"{', licensed' if r['allotted'] else ''})"
                         for r in sorted(both, key=lambda r: r["delta"])) or "none"))
        print(f"     the same family two-sided, after BH q=0.05: {len(bh2)} of {len(fam)} {bh2}")
        out_r["transforms"][t] = {
            "axes": out, "leaks_both_nulls": leaks, "leaks_bh_q05": bh,
            "leaks_bh_q05_two_sided": bh2,
            "moved_two_sided": [r["axis"] for r in sorted(both, key=lambda r: r["delta"])],
            "n_negative_any": sum(1 for r in fam if r["negative"]),
            "n_fixed_threshold": sum(1 for r in fam if r["leak_fixed"])}
    # T3 against T1 is the presentation-invariance contrast: two edits of the same kind, one of which leaks.
    # T3 against T2 is the paper's claim: a mechanical edit against a semantic one, on the same papers.
    for A, B in (("T3_lengthen", "T1_endmatter"), ("T3_lengthen", "T2_concede")):
        contrast(label, R, mu, sd, metrics, rng, out_r, A, B)
    res["rosters"][label] = out_r


def contrast(label, R, mu, sd, metrics, rng, out_r, A, B):
    """The two transforms against each other, paired within paper.

    "T3 leaks and T1 does not" is a claim about the difference between the two, and two separate tests --
    one that clears 0.05 and one that does not -- are not a test of it. So it is tested directly. The
    papers are the same papers and each pair of variant texts was scored in one sitting, so the difference
    of the two deltas is a within-paper contrast in which the shared baseline cancels algebraically; what
    is left is the panel reading two texts of one manuscript that differ only in which presentation edit
    was applied.

    The null is widened to match. `axis` returns re-run differences already scaled to a single treated
    delta, which carries 1.5 sigma^2; the paired contrast carries 2 when the baselines cancel and 3 when
    they do not, so the scaling is undone and the appropriate factor applied. Reusing the pool as returned
    would have made the null 13% too narrow, in the direction that manufactures significance.
    """
    if A not in TRANSFORMS or B not in TRANSFORMS:
        return
    if R.get("day_matched"):
        srcs = R.get("sources") or [R]
        same = []
        for S in srcs:
            for d in sorted(glob.glob(S["base"])):
                if not os.path.isdir(d):
                    continue
                pid = S.get("pid", os.path.basename)(d)
                dy = [sorted(panel_day(x) for x in glob.glob(f"{S['var'](pid, t)}/panel*")
                             if os.path.isdir(x)) for t in (A, B)]
                if all(dy):
                    same.append(dy[0] == dy[1])
        cancels = bool(same) and all(same)
        note = (f"{sum(same)}/{len(same)} papers have both variant panels in one sitting"
                if same else "no paper has both")
    else:
        cancels, note = True, "one baseline per paper, so it cancels by construction"
    f = 1.0 if cancels else math.sqrt(1.5)

    print(f"\n{label} / {A} minus {B}, paired within paper  ({note};"
          f" null widened x{f * math.sqrt(2):.3f} sigma_panel)")
    print(HEAD)
    rows = []
    for name, cols, is_allot in (("composite (all 12)", metrics, None),
                                 (f"{A}'s allotted ({len(LEGIT[A])})", sorted(LEGIT[A]), True),
                                 (f"{A}'s non-allotted ({len(metrics) - len(LEGIT[A])})",
                                  sorted(set(metrics) - set(LEGIT[A])), False)):
        # One axis call per transform, not one for the pair. The re-run reference belongs to the day a
        # delta was measured on, and these two arms do not always share a day; asking about them together
        # would make that reference ambiguous, which is the condition `matched_axis` asserts against.
        got = {t: axis(cols, R, mu, sd, transforms=(t,)) for t in (A, B)}
        scale = got[A][2]
        both = sorted(set(got[A][0][A]) & set(got[B][0][B]))
        if len(both) < 4:
            continue
        diff = {q: got[A][0][A][q] - got[B][0][B][q] for q in both}
        # The re-run reference is each paper's own, averaged over whichever of the two sittings measured it.
        # Both are estimates of one panel-pair spread on untouched text; averaging keeps the paper as the key,
        # which is what the exact sign null needs.
        rr = {}
        for q in set(got[A][1]) | set(got[B][1]):
            vs = [got[t][1][q] for t in (A, B) if q in got[t][1]]
            rr[q] = st.mean(vs) / scale * f
        r = test(name, len(cols), is_allot, diff, rr, rng)
        rows.append(r)
        print(row(r))
    out_r.setdefault("contrasts", {})[f"{A}-{B}"] = {
        "pair": [A, B], "baselines_cancel": cancels, "note": note, "axes": rows}
    if rows:
        g = rows[0]
        print(f"  -> on the composite the two differ by {g['delta']:+.4f} = {g['d_over_sd']:+.2f} null sd,"
              f" p_pool {g['p_pooled']:.4f}"
              f" -> {'DISTINGUISHABLE' if g['moved'] else 'not distinguishable'}")


def main():
    res = {"draws": DRAWS, "seed": SEED, "rosters": {}}
    for label, R in ROSTERS.items():
        roster(label, R, res)
    if SKIPPED:
        print(f"\nINCOMPLETE PANELS READ PAST: {len(SKIPPED)}. A panel needs every slot the ruler was "
              f"fitted on; these had fewer, so they are in no estimate above.")
        for pdir, got, want in sorted(SKIPPED):
            print(f"  {got}/{want} slots  {os.path.relpath(pdir, AN)}")
        res["incomplete_panels"] = [{"panel": os.path.relpath(d, AN), "slots": g, "expected": w}
                                    for d, g, w in sorted(SKIPPED)]
    json.dump(res, open(f"{AN}/pia_null.json", "w"), indent=1, default=float)
    print("\nwrote pia_null.json")


if __name__ == "__main__":
    main()

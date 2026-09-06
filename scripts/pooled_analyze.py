#!/usr/bin/env python3
"""The presentation arm at forty-eight papers, on the day-matched contrast, both corpora.

This is the primary read of the transform study. It differs from `analyse_n1.py` in two ways, and each was
forced by a measurement rather than chosen here:

  * The contrast is DAY-MATCHED. Each variant panel is differenced against baseline panels scored on the
    variant's own day. The measurement that forces this: untouched text reads
    0.213 z lower on 2026-09-01 than on 2026-08-31 with the paper held fixed, so a contrast spanning that
    boundary carries a day offset inside the treatment effect. Holding the day fixed costs one baseline
    panel's worth of precision and removes a bias, which is the trade this study should take.
  * The corpus spans BOTH arms -- sixteen accepted papers and thirty-two rejected submissions.
    The arithmetic that forces this: at sixteen papers the minimum detectable effect was
    about as large as the band the effect is judged against, so the design could not have resolved a
    transform whose true effect was half the band. Papers, not extra panels, buy that down.

The criterion is NOT re-chosen here. It was fixed before any of this was scored -- a transform is
presentation-invariant unless the absolute median composite delta leaves both reference bands AND at least
90% of papers keep their grade -- and the pre-registered band of 0.160 z is what the medians are compared
against. The day-matched re-run band is also printed, because it is the same quantity measured inside this
contrast and a reader will want it, but it is reported as a measurement and not substituted for the gate.
Swapping in a tighter band at analysis time would let the instrument's own precision decide the verdict.

The unit is the paper everywhere. A panel median over five slots is one reading of one text; the deltas
being averaged, bootstrapped and sign-tested are per-paper, and the bootstrap resamples papers rather than
readings for the same reason.

The corpus test is a genuine question rather than a robustness gesture: if presentation sensitivity is a
property of manuscripts sitting near an accept boundary, it should be visible in the accepted arm and
absent in the rejected one. Reported as a two-sample permutation test on the per-paper deltas, which is
the same test the old/new subset split already uses.

    python3 pooled_analyze.py [--json]
"""
from __future__ import annotations

import collections
import glob
import itertools
import json
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse_n1 import GRADE_NUM

AN = os.path.dirname(os.path.abspath(__file__))
CAL = "/path/to/workspace/paper_direction_98_calibration"
TRANSFORMS = ("T1_endmatter", "T2_concede", "T3_lengthen")
LABEL = {"T1_endmatter": "T1 figures -> end matter", "T2_concede": "T2 soften the claims",
         "T3_lengthen": "T3 join sentences"}
BAND_RERUN = 0.160        # pre-registered: MEDIAN |panel1 - panel2| on byte-identical text
BAND_RERUN_MEAN = 0.189   # pre-registered, same measurement, mean form -- the criterion names a mean
BAND_ADJACENT = 0.115     # pre-registered: the gap between adjacently ranked papers
# One variant panel against a two-panel baseline mean carries 1.5 sigma^2; a panel-against-panel re-run
# difference carries 2. So a reference measured on re-run pairs has to be shrunk by this factor before an
# arm's own spread is compared with it, or the arm is held to a band wider than its own noise.
MATCH = (1.5 / 2) ** 0.5
DRAWS = 20000
SEED = 20260901


def load():
    """The reading table, with a count of what it is missing.

    This reads a file that another script builds, and while an arm is draining that file is behind the disk by
    construction. Being behind is not an error; not knowing it is. A stale table once had this script report
    twenty-five papers while `pia_null.py`, which walks the review trees directly, reported thirty-two for the
    same estimand -- two answers to one question, which is the defect class this whole audit is about. So the
    gap is measured and printed rather than assumed away, and it is not made fatal, because refusing to run
    mid-drain would only mean nobody looks.
    """
    rows = json.load(open(f"{AN}/readings.json"))
    # Incomplete panels are dropped here and nowhere else. `readings.py` records whether every slot the
    # ruler was fitted on contributed; a panel missing slots is one reviewer's reading carrying a panel's
    # weight, and one such directory was briefly the largest single value in the rejected arm.
    bad = [r for r in rows if not r.get("complete", True)]
    if bad:
        print(f"DROPPED {len(bad)} incomplete panel(s), short of the full slot complement: "
              + ", ".join(f"{r['paper']}/{r['condition']}/{r['panel']}"
                          f" ({r.get('scored_slots')} slots)" for r in bad) + "\n")
    have = sum(r["slots"] for r in rows)
    rows = [r for r in rows if r.get("complete", True)]
    disk = sum(len(glob.glob(f"{AN}/{a}/reviews/*/*/panel*/R?.json"))
               for a in ("n1b_drift_5model", "n1c_reject_5model", "n1d_dayrep_5model"))
    disk += len(glob.glob(f"{AN}/n1_pia_5model/reviews/*/panel*/R?.json"))
    disk += len(glob.glob(f"{CAL}/reviews/*/panel*/R?.json"))
    if disk > have:
        print(f"NOTE: readings.json holds {have} reviews and {disk} are on disk -- {disk - have} newer "
              f"reviews are not in this analysis. Run `python3 readings.py` to fold them in.\n")
    return rows


def modal(grades):
    """The grade a venue reads off a panel: modal over its slots, ties broken DOWN toward Reject.

    Imported rule, not a new one -- `analyse_n1.modal_grade` is what produced every grade number already in
    the paper, and a second definition of "the panel's grade" would give the appendix a figure that no other
    script in the tree agrees with.
    """
    gs = [g for g in grades.values() if g in GRADE_NUM]
    if not gs:
        return None
    best = max(gs.count(g) for g in set(gs))
    return min((g for g in set(gs) if gs.count(g) == best), key=lambda g: GRADE_NUM[g])


def same_day_pair(panels, day=None):
    """-> the two baseline panels a day-matched contrast uses for one paper, in panel order, or None.

    One rule in one place, because three readings of the baseline depend on it: the delta, the re-run band and
    the grade ceiling. `day` names the variant's day when there is a variant to match; without it the pair is
    the paper's first two panels that share any day, which is what an untouched paper offers.

    Two panels, not every same-day panel that exists. A later pass added two more baseline panels for some
    papers of the accepted arm, so taking all of them would give those papers a four-panel baseline and the
    rest two, and the rejected corpus only ever has two -- an accepted-against-rejected comparison would then
    be partly a comparison of baseline precision. Not panel1 and panel2 by name either: half of one arm's
    variant panels were scored the day after that paper's first two baseline panels, so naming the panels
    drops those papers from the contrast without saying so.
    """
    for dy in ([day] if day else sorted({p["day"] for p in panels.values()})):
        got = [p for _, p in sorted(panels.items()) if p["day"] == dy][:2]
        if len(got) == 2:
            return got
    return None


def modal_over(panels):
    """The grade a venue reads off more than one panel of the same text: the mode over every slot reading.

    `analyse_n1.modal_grade` pools every review in a baseline directory rather than taking a mode of the
    per-panel modes, and this is that rule restricted to the panels this contrast uses. A mode of two modes is
    a different statistic, and when the two disagree it has no tie-break that is not arbitrary.
    """
    merged = {}
    for i, pan in enumerate(panels):
        for slot, g in pan["grades"].items():
            merged[f"{i}|{slot}"] = g
    return modal(merged)


def matched_pairs(rows, transform):
    """-> [{paper, corpus, day, delta, grade_base, grade_var}] one row per paper, day held fixed.

    The variant is the drift arm's single variant panel; the baseline is the mean over that arm's baseline
    panels RESTRICTED to the variant's own day. Papers whose baseline panels were all scored on another day
    contribute nothing, because for them this contrast does not exist.
    """
    by = collections.defaultdict(dict)
    for r in rows:
        src, _, pn = r["panel"].partition("/")
        if src in ("n1b", "n1c"):
            by[r["paper"]].setdefault(r["condition"], {})[pn] = r
    out = []
    for pid, conds in sorted(by.items()):
        var = (conds.get(transform) or {}).get("panel1")
        base = conds.get("baseline") or {}
        if not var:
            continue
        same = same_day_pair(base, var["day"])
        if not same:
            continue
        out.append({"paper": pid, "corpus": var.get("corpus", "accepted"), "day": var["day"],
                    "n_base": len(same), "delta": var["z"] - st.mean(b["z"] for b in same),
                    "grade_var": modal(var["grades"]), "grade_base": modal_over(same)})
    return out


def rerun_band(rows, only=None):
    """The day-matched re-run band: median |difference| between the two baseline panels the contrast uses.

    `only` restricts the paper set, for the one comparison that needs this roster's precision measured on
    another roster's papers rather than on all of them.

    The same pair the deltas are differenced against, one per paper. Every same-day pair that exists would
    weight a four-panel paper six times a two-panel one, and would be the band of a baseline this study does
    not use.

    Measured, printed, and not used as a threshold. The pre-registered band was set before scoring and is
    what the criterion names; this is here so a reader can see what the instrument's precision actually is
    inside the contrast being reported.
    """
    diffs = []
    for pid, panels in _baseline_panels(rows).items():
        if only is not None and pid not in only:
            continue
        pair = same_day_pair(panels)
        if pair:
            diffs.append(abs(pair[0]["z"] - pair[1]["z"]))
    if not diffs:
        return None
    return {"n_pairs": len(diffs), "median": round(st.median(diffs), 4), "mean": round(st.mean(diffs), 4),
            "median_matched": round(st.median(diffs) * MATCH, 4),
            "mean_matched": round(st.mean(diffs) * MATCH, 4)}


def grade_retest(rows):
    """Modal-grade agreement on byte-identical baseline text, same day: the grade conjunct's own ceiling."""
    same = []
    for pid, panels in _baseline_panels(rows).items():
        pair = same_day_pair(panels)
        if not pair:
            continue
        ga, gb = modal(pair[0]["grades"]), modal(pair[1]["grades"])
        if ga and gb:
            same.append(ga == gb)
    return {"n_pairs": len(same), "agreement": round(sum(same) / len(same), 4)} if same else None


def _baseline_panels(rows):
    by = collections.defaultdict(dict)
    for r in rows:
        src, _, pn = r["panel"].partition("/")
        if src in ("n1b", "n1c") and r["condition"] == "baseline":
            by[r["paper"]][f"{src}/{pn}"] = r
    return by


def sign_p(d):
    """Two-sided exact sign test, zeros dropped."""
    nz = [x for x in d if x != 0]
    n, k = len(nz), sum(1 for x in nz if x < 0)
    if not n:
        return 1.0
    c = lambda a, b: math.comb(a, b)
    tail = lambda m: sum(c(n, i) for i in range(m + 1)) / 2 ** n
    return round(min(1.0, 2 * tail(min(k, n - k))), 4)


def boot_ci(d, rng):
    """Cluster bootstrap of the median over papers. The paper is the cluster because it is the unit."""
    import numpy as np
    a = np.asarray(d, dtype=float)
    med = np.median(a[rng.integers(0, len(a), size=(DRAWS, len(a)))], axis=1)
    return [round(float(np.percentile(med, 2.5)), 4), round(float(np.percentile(med, 97.5)), 4)]


def perm2(a, b, rng):
    """Two-sample permutation test on the difference of medians. Exact when the split count allows it."""
    import numpy as np
    pool = np.asarray(list(a) + list(b), dtype=float)
    n = len(a)
    obs = float(np.median(pool[:n]) - np.median(pool[n:]))
    if math.comb(len(pool), n) <= 200000:
        stats = [float(np.median(pool[list(idx)]) - np.median(np.delete(pool, list(idx))))
                 for idx in itertools.combinations(range(len(pool)), n)]
        exact = True
    else:
        stats = []
        for _ in range(DRAWS):
            p = rng.permutation(pool)
            stats.append(float(np.median(p[:n]) - np.median(p[n:])))
        exact = False
    ge = sum(1 for s in stats if abs(s) >= abs(obs) - 1e-12)
    p = ge / len(stats) if exact else (ge + 1) / (len(stats) + 1)
    return {"diff": round(obs, 4), "p": round(p, 4), "exact": exact, "n_a": n, "n_b": len(pool) - n}


def doses(transform):
    """-> {paper: edits} for one transform, read from the two variant manifests.

    The manifests are what the transform script wrote when it built the variants, so this is the dose as
    applied rather than a re-count of the text. Both corpora are read into one map because the paper ids do
    not collide -- the accepted arm is keyed by arxiv identifier, the rejected arm by its arm-blind label.
    """
    out = {}
    for man in ("pia_variants/manifest.json", "pia_variants_reject/manifest.json"):
        path = f"{AN}/{man}"
        if not os.path.exists(path):
            continue
        for pid, v in json.load(open(path))["variants"].items():
            e = (v.get(transform) or {}).get("edits")
            if e is not None:
                out[pid] = e
    return out


def dose_link(pairs, transform, rng):
    """Does a paper's delta track how much of the transform it received?

    The one moderator available that is a property of the treatment rather than of the schedule. A subgroup
    whose delta is larger and whose dose is also larger has an explanation; a subgroup whose delta is larger at
    the same dose does not. Reported as a rank correlation with a permutation p, plus the per-group median dose
    so the two readings can be told apart.

    Spearman rather than Pearson because the dose distributions are right-skewed and the question is monotone.
    A negative rho means more edits, more cost, which is the direction a dose-response would take here.
    """
    import numpy as np
    dd = doses(transform)
    xy = [(dd[p["paper"]], p["delta"]) for p in pairs if p["paper"] in dd]
    if len(xy) < 6:
        return None
    x, y = np.asarray([a for a, _ in xy], float), np.asarray([b for _, b in xy], float)

    # Ties averaged. Edit counts tie heavily -- a third of this arm shares a value with another paper -- and
    # argsort of argsort would rank tied papers by their position in the array, so the correlation would depend
    # on the order the manifests happened to be read in. It moved this arm's rho in the third decimal.
    def rank(v):
        order = np.argsort(v, kind="stable")
        r = np.empty(len(v))
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            r[order[i:j + 1]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rho = lambda a, b: float(np.corrcoef(rank(a), rank(b))[0, 1])
    obs = rho(x, y)
    null = [rho(x, rng.permutation(y)) for _ in range(DRAWS)]
    p = (sum(1 for s in null if abs(s) >= abs(obs) - 1e-12) + 1) / (DRAWS + 1)
    return {"n": len(xy), "rho": round(obs, 4), "p": round(p, 4),
            "dose_median": round(float(np.median(x)), 1),
            "dose_range": [int(x.min()), int(x.max())]}


def subgroups(pairs):
    """-> the per-paper deltas split three ways: the accepted arm's old eight, its new eight, the rejected arm.

    The old/new label is read from `sitting_check.json`, which is where the study already records it, rather
    than re-derived here. The rule behind it was fixed before scoring -- rank the sixteen accepted papers by
    baseline composite and take every other one -- so the two halves are matched on the panel's own read of
    quality, and `sitting_check.py` checks that the papers scored in the earlier sitting are exactly the papers
    the rule names. Re-deriving it in a second place is how a label comes to mean two things.

    Why three groups and not two: at sixteen papers the T1 arm's whole effect sat in the old half, and the
    obvious reading of that was a day offset, since the halves were scored on different days. Under the
    day-matched contrast each half is differenced against its own day's baselines, so if the gap is still there
    it is not the boundary. The rejected arm is a third group that shares no sitting with either, which is what
    makes it useful: it says whether the old half is unusual or the new half is.

    These are subgroup comparisons and they were not pre-registered. They are reported to locate variance, and
    no verdict rests on them; the pooled estimate is the answer the expansion was bought for.
    """
    old = set(json.load(open(f"{AN}/sitting_check.json"))["old_subset"])
    g = {"accepted_old": [], "accepted_new": [], "rejected": []}
    for p in pairs:
        if p["corpus"] == "rejected":
            g["rejected"].append(p)
        else:
            g["accepted_old" if p["paper"] in old else "accepted_new"].append(p)
    return g


def variant_panel_noise(rows):
    """Is a panel noisier on transformed text than on untouched text? Measured, because the answer decides
    what an arm's excess spread means.

    An arm can be more dispersed than the panel's re-run noise for two reasons that the day-matched contrast
    cannot separate on its own, since it scores one variant panel per paper: the transform costs different
    papers different amounts, or the panel simply agrees with itself less on transformed text. The first arm of
    the study scored TWO panels of each variant text, so the second reason is directly measurable there --
    two readings of one text, same day, with the treatment held fixed.

    Both figures below are same-day pairs, so neither carries the day offset, and both are per-panel standard
    deviations recovered from a pair difference by dividing by root two.
    """
    out = {}
    for tag, cond_ok, label in (("cal", lambda c: c == "baseline", "untouched"),
                                ("n1", lambda c: c != "baseline", "transformed")):
        by = collections.defaultdict(dict)
        for r in rows:
            if r["panel"].startswith(tag + "/") and cond_ok(r["condition"]):
                by[(r["paper"], r["condition"])][r["panel"]] = r
        d = []
        for v in by.values():
            k = sorted(v)[:2]
            if len(k) == 2 and v[k[0]]["day"] == v[k[1]]["day"]:
                d.append(v[k[0]]["z"] - v[k[1]]["z"])
        if len(d) > 1:
            out[label] = {"n_pairs": len(d), "per_panel_sd": round(st.stdev(d) / math.sqrt(2), 4)}
    if len(out) == 2:
        out["ratio_transformed_to_untouched"] = round(out["transformed"]["per_panel_sd"]
                                                      / out["untouched"]["per_panel_sd"], 3)
    return out


def heterogeneity(pairs, rows, rng):
    """Is an arm's per-paper spread larger than the panel's own noise can account for?

    This is the question the criterion's pre-registered wording asks without meaning to. It names a mean of
    absolute deltas, which is a dispersion statistic: an arm can exceed it while its median sits at zero, so
    what such an arm reports is that papers respond differently, not that the panel moved.

    The comparison is legitimate because the two quantities are orthogonal by construction. A paper's delta is
    the variant panel against the mean of its two baseline panels; its re-run difference is those two panels
    against each other. A sum and a difference of two equal-variance independent readings are uncorrelated, and
    the variant panel enters only the first. Under no treatment heterogeneity the delta carries 1.5 sigma^2 and
    the re-run difference 2, so the ratio of their variances is 0.75 and any excess over that is either a
    variant panel noisier than a baseline panel or a transform whose cost differs from paper to paper.

    Reported as the ratio to that null with a cluster bootstrap over papers, because the paper is the unit and
    both quantities are measured on the same papers.
    """
    import numpy as np
    bp = _baseline_panels(rows)
    a, b = [], []
    for p in pairs:
        pair = same_day_pair(bp.get(p["paper"], {}))
        if pair:
            a.append(p["delta"])
            b.append(pair[0]["z"] - pair[1]["z"])
    if len(a) < 4:
        return None
    A, B = np.asarray(a), np.asarray(b)
    ratio = lambda x, y: float(x.var(ddof=1) / (0.75 * y.var(ddof=1)))
    obs = ratio(A, B)
    idx = rng.integers(0, len(A), size=(DRAWS, len(A)))
    draws = np.sort([ratio(A[i], B[i]) for i in idx])
    return {"n": len(A), "sd_delta": round(float(A.std(ddof=1)), 4),
            "sd_rerun": round(float(B.std(ddof=1)), 4), "ratio_to_null": round(obs, 3),
            "ci95": [round(float(np.percentile(draws, 2.5)), 3), round(float(np.percentile(draws, 97.5)), 3)],
            "share_at_or_below_1": round(float((draws <= 1).mean()), 4)}


def reference_field(rows):
    """-> {paper: baseline composite} over every paper with a day-matched baseline pair.

    This is the untouched field a variant is ranked inside: one value per paper, the mean of the two
    baseline panels the contrast differences against, so a paper with four panels does not get a
    steadier position in the field than a paper with two.

    The field is NOT day-centred. Papers were scored in more than one sitting and the sitting is worth a
    real offset, so the field's spacing carries between-day variance the transforms cannot cause. That
    inflates the gaps, and a wider gap means a given shift in z crosses fewer papers, so the displacement
    measured here is smaller than a same-day field would give. Conservative and ecologically honest: a
    venue's own list is built across sittings too. The day-centred field is computed beside it as a
    robustness value rather than substituted for it.
    """
    out = {}
    for pid, panels in _baseline_panels(rows).items():
        pair = same_day_pair(panels)
        if pair:
            out[pid] = st.mean(x["z"] for x in pair)
    return out


def displacement(pairs, rows, centred=False):
    """How far each variant moves in the untouched reference field, in places.

    A paper's baseline rank is its position among the untouched papers; its variant rank is where the
    variant's own composite would fall in that same field with the paper's own baseline removed, since a
    paper does not compete with itself. Positive means the variant ranks better.
    """
    field = reference_field(rows)
    if centred:
        byday = collections.defaultdict(list)
        for pr in pairs:
            byday[pr["day"]].append(pr["paper"])
        day_of = {pr["paper"]: pr["day"] for pr in pairs}
        mus = {d: st.mean(field[q] for q in ps if q in field) for d, ps in byday.items()
               if any(q in field for q in ps)}
        field = {q: v - mus.get(day_of.get(q), 0.0) for q, v in field.items()}
    disp = []
    for pr in pairs:
        pid = pr["paper"]
        if pid not in field:
            continue
        others = sorted((v for q, v in field.items() if q != pid), reverse=True)
        base_r = sum(1 for v in others if v > field[pid])
        var_r = sum(1 for v in others if v > field[pid] + pr["delta"])
        disp.append({"paper": pid, "places": base_r - var_r})
    if not disp:
        return None
    d = [x["places"] for x in disp]
    return {"n": len(d), "n_field": len(field), "median": round(st.median(d), 1),
            "mean": round(st.mean(d), 2), "worst": min(d), "best": max(d),
            "n_moved": sum(1 for x in d if x != 0),
            "n_down": sum(1 for x in d if x < 0), "n_up": sum(1 for x in d if x > 0),
            "per_paper": {x["paper"]: x["places"] for x in disp}}


def grade_flip_null(rows):
    """The flip rate with the treatment removed: one untouched reading against two others, same day.

    `grade_cells` calls a cell flipped when the variant's grade differs from both baseline readings, and
    reports beside it the rate at which those two baseline readings differ from each other. The second is a
    single disagreement and the first is a conjunction of two, so the comparison is not like for like and
    it understates the arm. This is the missing row: a third untouched reading in the place the variant
    occupies, differing from both of the other two.

    Every assignment of the available panels to (probe, pair) is used rather than one, because picking one
    would be choosing a reference. Papers with fewer than three same-day baseline panels cannot supply the
    statistic at all and are counted separately, so the row can say what it is measured on.
    """
    bypaper = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in rows:
        src, _, pn = r["panel"].partition("/")
        if src in ("n1b", "n1c") and r["condition"] == "baseline":
            bypaper[r["paper"]][r["day"]][pn] = r
    hits = total = 0
    usable = []
    for pid, days in sorted(bypaper.items()):
        best = max(days.values(), key=len)
        if len(best) < 3:
            continue
        usable.append(pid)
        panels = sorted(best)
        for probe in panels:
            others = [q for q in panels if q != probe]
            for i in range(len(others)):
                for j in range(i + 1, len(others)):
                    a, b = best[others[i]], best[others[j]]
                    v = best[probe]
                    for slot, gv in sorted(v["grades"].items()):
                        ga, gb = a["grades"].get(slot), b["grades"].get(slot)
                        if not (ga and gb):
                            continue
                        total += 1
                        if gv != ga and gv != gb:
                            hits += 1
    return {"n_papers": len(usable), "n_papers_without": len(bypaper) - len(usable), "papers": usable,
            "n_comparisons": total, "n_flipped": hits,
            "rate": round(hits / total, 4) if total else None}


def grade_cells(rows, transform, only=None):
    """Paired grade flips at the level of one reviewer's grade, against the instrument's own retest rate.

    `only` restricts the paper set. The one caller that passes it reads the arms on the papers the
    treatment-free reference can be measured on, and it has to be the same code that defines a flip
    everywhere else, or the comparison would be between two definitions rather than two populations.

    A cell is (paper, slot). It flips when the variant's grade at that slot differs from BOTH of the
    same-day baseline panels' grades at that slot. Differing from one of two readings of identical text is
    inside what the instrument does to itself, and the point of the paragraph this feeds is exactly that
    comparison, so the denominator has to be the same cells: `retest_disagree` counts the cells where the
    two baseline readings disagree with each other. No tie-break is needed and none is invented.
    """
    bypaper = collections.defaultdict(dict)
    for r in rows:
        src, _, pn = r["panel"].partition("/")
        if src in ("n1b", "n1c") and (only is None or r["paper"] in only):
            bypaper[r["paper"]].setdefault(r["condition"], {})[pn] = r
    flipped, total, retest, rtotal = [], 0, 0, 0
    # Steps and agreements are accumulated one reading against one reading on BOTH sides: each variant
    # grade is compared to each of the two baseline grades in turn, and the re-run compares the two
    # baseline grades to each other. Differencing the variant against the mean of the pair instead would
    # hand it the smaller variance of a mean-of-two, and every arm would then move the grade less than a
    # re-run by construction rather than by measurement.
    steps, agree, rsteps, ragree = [], [], [], []
    for pid, conds in sorted(bypaper.items()):
        var = (conds.get(transform) or {}).get("panel1")
        if not var:
            continue
        pair = same_day_pair(conds.get("baseline") or {}, var["day"])
        if not pair or len(pair) != 2:
            continue
        for slot, gv in sorted(var["grades"].items()):
            ga, gb = pair[0]["grades"].get(slot), pair[1]["grades"].get(slot)
            if not (ga and gb):
                continue
            total += 1
            if gv != ga and gv != gb:
                flipped.append(f"{pid}/{slot}")
            for g in (ga, gb):
                agree.append(1.0 if gv == g else 0.0)
                if gv in GRADE_NUM and g in GRADE_NUM:
                    steps.append(abs(GRADE_NUM[gv] - GRADE_NUM[g]))
    for pid, conds in sorted(bypaper.items()):
        pair = same_day_pair(conds.get("baseline") or {})
        if not pair or len(pair) != 2:
            continue
        for slot in sorted(set(pair[0]["grades"]) & set(pair[1]["grades"])):
            rtotal += 1
            ga, gb = pair[0]["grades"][slot], pair[1]["grades"][slot]
            if ga != gb:
                retest += 1
            ragree.append(1.0 if ga == gb else 0.0)
            if ga in GRADE_NUM and gb in GRADE_NUM:
                rsteps.append(abs(GRADE_NUM[ga] - GRADE_NUM[gb]))
    return {"n_cells": total, "n_flipped": len(flipped), "cells": flipped,
            "rate": round(len(flipped) / total, 4) if total else None,
            "retest_cells": rtotal, "retest_disagree": retest,
            "retest_rate": round(retest / rtotal, 4) if rtotal else None,
            "mean_step": round(st.mean(steps), 4) if steps else None,
            "mean_step_rerun": round(st.mean(rsteps), 4) if rsteps else None,
            "agreement": round(st.mean(agree), 4) if agree else None,
            "agreement_rerun": round(st.mean(ragree), 4) if ragree else None,
            "n_comparisons": len(steps)}


def roster_matched(rows, rng):
    """This roster read on exactly the papers the other roster scored.

    The second roster is in the paper as the vendor-diversity reading: eight slots over six vendors, run to
    show that a finding from five slots is not a property of two providers. It was run on eight papers and
    this roster now covers forty-eight, so a difference between the two readings has been a difference of
    instrument and of paper set together. Those eight are also the group the subgroup test names, which is
    the corpus half where the figure arm costs something, so the confound has been running in the direction
    that makes the two instruments look as though they disagree about which arm is larger.

    Restricting this roster to those eight papers removes the paper set from the contrast. What it does not
    supply is a shared axis: the re-run band measured on eight papers alone is a median of eight single
    |panel - panel| gaps, appendix E already declines to quote this roster's value of it for that reason, and
    dividing by it inflates every ratio here about fourfold. So each side is shown against its own
    PRE-REGISTERED band, the measured one is carried beside it as a diagnostic, and the sign is the
    comparison to lean on. The paper list comes from the other roster's own output; typing it here would let
    it drift from the arm it describes.
    """
    path = f"{AN}/n2_pia_cursor8/n2_analysis.json"
    if not os.path.exists(path):
        return None
    other = json.load(open(path, encoding="utf-8"))
    papers = set()
    for T in other["transforms"].values():
        papers |= set(T.get("per_paper") or {})
    if not papers:
        return None
    band = rerun_band(rows, only=papers)
    out = {"papers": sorted(papers), "source": "n2_pia_cursor8/n2_analysis.json",
           "five_slot_band": band, "eight_slot_band": other["rerun_band_this_roster"],
           "eight_slot_grade_band": other["grade_retest_this_roster"]["mean_abs_step"], "arms": {}}
    for t in TRANSFORMS:
        pairs = [p for p in matched_pairs(rows, t) if p["paper"] in papers]
        five = block(pairs, rng)
        if not five:
            continue
        g5 = grade_cells(rows, t, only=papers)
        T8 = (other["transforms"].get(t) or {})
        if not T8:
            continue
        # Each ratio is to its own roster's pre-registered band, not to the band measured on these eight
        # papers: see the docstring. The grade ratio is to each roster's own re-run grade step.
        b8 = other["rerun_band_this_roster"]
        gb8 = other["grade_retest_this_roster"]["mean_abs_step"]
        out["arms"][t] = {
            "five_slot": five,
            "five_slot_vs_own_band": round(five["median_abs"] / BAND_RERUN, 3),
            "five_slot_grade": {k: g5[k] for k in ("mean_step", "mean_step_rerun", "agreement",
                                                   "agreement_rerun", "n_comparisons")},
            "five_slot_grade_ratio": (round(g5["mean_step"] / g5["mean_step_rerun"], 3)
                                      if g5["mean_step"] and g5["mean_step_rerun"] else None),
            "eight_slot": {"n": T8["n_negative"] + T8["n_positive"], "median": T8["median_delta"],
                           "median_abs": T8["median_abs_delta"], "ci95": T8["delta_ci95"],
                           "negative": T8["n_negative"], "sign_p": T8["sign_test_p"]},
            "eight_slot_vs_own_band": round(T8["median_abs_delta"] / b8, 3),
            "eight_slot_grade": {"mean_step": T8["grade"]["mean_abs_step"], "mean_step_rerun": gb8,
                                 "modal_grade_kept": T8["grade"]["modal_grade_kept"]},
            "eight_slot_grade_ratio": round(T8["grade"]["mean_abs_step"] / gb8, 3),
            "same_sign": bool(five["median"] * T8["median_delta"] > 0)}
    # The third reading of the same eight papers, on this roster, in a later sitting. It is here so the
    # ordering question can be asked of one instrument as well as of two: an ordering that does not survive
    # re-scoring the same texts on the same roster was never a property of the roster.
    rep = f"{AN}/dayrep_analysis.json"
    DAYREP = json.load(open(rep, encoding="utf-8")) if os.path.exists(rep) else None
    nul = f"{AN}/pia_null.json"
    NULLS = json.load(open(nul, encoding="utf-8")) if os.path.exists(nul) else {}
    if DAYREP:
        R = DAYREP
        for t, r in (R.get("arms") or {}).items():
            if t in out["arms"] and "later" in (r or {}):
                out["arms"][t]["five_slot_later_sitting"] = {
                    "n": r["n"], "median": r["later"]["median"], "ci95": r["later"]["ci95"],
                    "negative": r["later"]["negative"], "sign_p": r["later"]["sign_p"],
                    # The day lives per paper in that file, and every paper in the arm shares it.
                    "day": sorted({v["later_day"] for v in r["per_paper"].values()})}
    # Which arm costs more, taken as a paired difference rather than as two medians. Comparing the medians
    # of two arms measured against two baselines is not a test of the difference between the arms, and here it
    # is not even a consistent description of it: unpaired, the later sitting puts figure relocation ahead;
    # paired, the same eight papers put sentence joining ahead in both sittings. The paired readings live in
    # the two files that compute them, so they are collected here rather than recomputed.
    order = {}
    for lbl, when in (("5model_pooled", "five slots, both corpora"),
                      ("5model_eight", "five slots, the eight the other roster covers"),
                      ("8slot", "eight slots, the eight it covers")):
        for key, C in sorted(((NULLS.get("rosters") or {}).get(lbl, {}).get("contrasts") or {}).items()):
            A, B = C["pair"]
            if {A, B} != {"T1_endmatter", "T3_lengthen"}:
                continue
            ax = next((x for x in C["axes"] if x["axis"].startswith("composite")), None)
            if ax:
                order[lbl] = {
                    "reading": when, "pair": [A, B], "n": ax["n_papers"], "delta": ax["delta"],
                    "sign": [ax["n_negative"], ax["n_positive"]],
                    # Against the panel's own re-run noise, which is the study's declared null.
                    "p_vs_rerun_null": ax["p_pooled"], "p_exact_vs_rerun_null": ax["p_exact"],
                    "larger": A if ax["delta"] < 0 else B,
                    "separable_vs_rerun_null": ax["moved"]}
    # And the same difference against the observed differences' own signs, which is the conservative test and
    # the one that carries paper-to-paper heterogeneity. It exists for the eight papers in both sittings.
    ao = (DAYREP or {}).get("arm_ordering") or {}
    for when in ("original", "later"):
        if when in ao:
            w = ao[when]
            order[f"5model_eight_{when}_sitting_sign_test"] = {
                "reading": f"five slots, the eight, {when} sitting, sign test on the paired differences",
                "pair": ao["pair"], "n": ao["n"], "delta": w["median"], "ci95": w["ci95"],
                "sign": [w["negative"], ao["n"] - w["negative"]], "p_sign_test": w["p"],
                "larger": w["larger"], "separable_by_sign_test": w["p"] < 0.05}
    if order:
        larger = {v["larger"] for v in order.values() if v.get("delta")}
        out["arm_ordering"] = dict(
            order,
            same_arm_larger_everywhere=len(larger) == 1,
            larger_arm=sorted(larger)[0] if len(larger) == 1 else None,
            # The two rosters do not disagree about the ordering. Neither of them resolves it on eight
            # papers, and the reading that resolves it has forty-six.
            separable_on_eight_papers=any(v.get("separable_by_sign_test") for v in order.values()
                                          if v["n"] == 8),
            separable_on_full_corpus=bool((order.get("5model_pooled") or {})
                                          .get("separable_vs_rerun_null")))
    return out


def block(pairs, rng):
    d = [p["delta"] for p in pairs]
    if not d:
        return None
    kept = [p for p in pairs if p["grade_base"] and p["grade_var"]]
    same = sum(1 for p in kept if p["grade_base"] == p["grade_var"])
    return {"n": len(d), "median": round(st.median(d), 4), "mean": round(st.mean(d), 4),
            # The criterion as pre-registered names mean |delta|; every table in the paper has reported the
            # median of the signed delta. They are a dispersion statistic and a location statistic, they do
            # not answer the same question, and at this sample size they no longer agree. Both are computed
            # here, each against the form of the reference that matches it, and neither is chosen by verdict.
            "median_abs": round(st.median([abs(x) for x in d]), 4),
            "mean_abs": round(st.mean([abs(x) for x in d]), 4),
            "vs_band_median_abs": round(st.median([abs(x) for x in d]) / BAND_RERUN, 3),
            "vs_band_mean_abs": round(st.mean([abs(x) for x in d]) / BAND_RERUN_MEAN, 3),
            "sd": round(st.stdev(d), 4) if len(d) > 1 else None,
            "ci95": boot_ci(d, rng), "negative": sum(1 for x in d if x < 0),
            "positive": sum(1 for x in d if x > 0), "sign_p": sign_p(d),
            "vs_rerun_band": round(abs(st.median(d)) / BAND_RERUN, 3),
            "outside_both_bands": bool(abs(st.median(d)) > BAND_RERUN and abs(st.median(d)) > BAND_ADJACENT),
            "grade_kept": f"{same}/{len(kept)}",
            "grade_retention": round(same / len(kept), 4) if kept else None}


def main():
    import numpy as np
    rng = np.random.default_rng(SEED)
    rows = load()
    out = {"band_rerun_preregistered": BAND_RERUN, "band_adjacent_preregistered": BAND_ADJACENT,
           "rerun_band_measured_day_matched": rerun_band(rows),
           "grade_retest_day_matched": grade_retest(rows),
           "grade_flip_null": grade_flip_null(rows),
           "variant_panel_noise": variant_panel_noise(rows), "arms": {}, "corpus_test": {},
           "subgroup_test": {}, "grade_cells_any_transform": None,
           "roster_matched": roster_matched(rows, rng)}

    for t in TRANSFORMS:
        pairs = matched_pairs(rows, t)
        acc = [p for p in pairs if p["corpus"] == "accepted"]
        rej = [p for p in pairs if p["corpus"] == "rejected"]
        out["arms"][t] = {"pooled": block(pairs, rng), "accepted": block(acc, rng),
                          "rejected": block(rej, rng), "heterogeneity": heterogeneity(pairs, rows, rng),
                          "dose_link": dose_link(pairs, t, rng),
                          # Pooled over both corpora the correlation could be a corpus contrast wearing a
                          # dose label, since the two arms differ in both. Measured inside each corpus as
                          # well, where there is no corpus term left to carry it.
                          "dose_link_accepted": dose_link(acc, t, rng),
                          "dose_link_rejected": dose_link(rej, t, rng),
                          # The composite is in z and a venue reads a list. Displacement converts one into
                          # the other: how many places the variant moves in the untouched field.
                          "displacement": displacement(pairs, rows),
                          "displacement_day_centred": displacement(pairs, rows, centred=True),
                          "grade_cells": grade_cells(rows, t),
                          "per_paper": {p["paper"]: round(p["delta"], 4) for p in pairs}}
        if len(acc) >= 4 and len(rej) >= 4:
            out["corpus_test"][t] = perm2([p["delta"] for p in acc], [p["delta"] for p in rej], rng)

        g = subgroups(pairs)
        dl = lambda k: [p["delta"] for p in g[k]]
        dd = doses(t)
        s = {"groups": {k: {"n": len(v), "median": round(st.median([p["delta"] for p in v]), 4),
                            "negative": sum(1 for p in v if p["delta"] < 0),
                            "positive": sum(1 for p in v if p["delta"] > 0),
                            "sign_p": sign_p([p["delta"] for p in v]),
                            # The dose sits beside the delta because a group with a larger effect and a
                            # larger dose is a dose-response, and a group with a larger effect at the same
                            # dose is unexplained variance. The table should not make a reader guess which.
                            "dose_median": (round(st.median([dd[p["paper"]] for p in v if p["paper"] in dd]), 1)
                                            if any(p["paper"] in dd for p in v) else None)}
                        for k, v in g.items() if v}}
        # Two comparisons, because they answer different questions. The first is the sixteen-paper finding
        # re-run inside a contrast that holds the day fixed. The second asks whether the old eight are the
        # arm: their forty companions, from both sittings and both corpora, pooled against them.
        if len(g["accepted_old"]) >= 4 and len(g["accepted_new"]) >= 4:
            s["old_vs_new_accepted"] = perm2(dl("accepted_old"), dl("accepted_new"), rng)
        rest = dl("accepted_new") + dl("rejected")
        if len(g["accepted_old"]) >= 4 and len(rest) >= 4:
            s["old_vs_everything_else"] = perm2(dl("accepted_old"), rest, rng)
        out["subgroup_test"][t] = s

    # A cell that flips under three edits with nothing in common is not reporting any of them; it is a
    # grade sitting on a boundary. So the union across transforms is the quantity worth reporting, and the
    # retest rate on identical text is what it has to be read against.
    ever = set()
    for t in TRANSFORMS:
        ever |= set(out["arms"][t]["grade_cells"]["cells"])
    ncells = max(out["arms"][t]["grade_cells"]["n_cells"] for t in TRANSFORMS)
    rc = out["arms"][TRANSFORMS[0]]["grade_cells"]
    # How much of an arm's flipping is the arm and how much is the cell. A cell that flips under an edit
    # and also under an unrelated edit of the same paper is telling us about the cell, and the three edits
    # here are independent of each other by construction, so the shared share bounds how much of any arm's
    # flip count can be read as a response to that arm's own edit.
    sets = {t: set(out["arms"][t]["grade_cells"]["cells"]) for t in TRANSFORMS}
    shared = {t: len(sets[t] & set().union(*(sets[u] for u in TRANSFORMS if u != t))) for t in TRANSFORMS}
    allthree = set.intersection(*sets.values())
    fnull = out["grade_flip_null"]
    fnull["arms_on_the_same_papers"] = {
        t: {k: grade_cells(rows, t, only=set(fnull["papers"]))[k] for k in ("n_cells", "n_flipped", "rate")}
        for t in TRANSFORMS}

    out["grade_cells_any_transform"] = {
        "n_ever_flipped": len(ever), "n_cells": ncells,
        "rate": round(len(ever) / ncells, 4) if ncells else None,
        "retest_cells": rc["retest_cells"], "retest_disagree": rc["retest_disagree"],
        "retest_rate": rc["retest_rate"],
        "per_transform": {t: out["arms"][t]["grade_cells"]["n_flipped"] for t in TRANSFORMS},
        "shared_with_another_arm": shared,
        "shared_share": {t: round(shared[t] / len(sets[t]), 4) if sets[t] else None for t in TRANSFORMS},
        "flipped_under_all_three": len(allthree)}

    if "--json" in sys.argv:
        json.dump(out, sys.stdout, indent=1)
        return 0

    b = out["rerun_band_measured_day_matched"]
    g = out["grade_retest_day_matched"]
    print("DAY-MATCHED CONTRAST, both corpora. Unit = paper. Gate = the pre-registered bands.\n")
    print(f"re-run band, measured in this contrast: median |delta| between the two baseline panels the "
          f"contrast uses = {b['median']:.4f} z over {b['n_pairs']} papers   (gate stays {BAND_RERUN})")
    print(f"modal-grade agreement on identical text: {g['agreement']:.3f} over {g['n_pairs']} papers "
          f"  (the 90% conjunct's own ceiling)\n")
    hdr = f"{'arm':26s} {'corpus':10s} {'n':>3s} {'median':>8s} {'ci95':>18s} {'-/+':>7s} {'signp':>7s} {'/band':>6s} {'grade':>7s}"
    print(hdr)
    print("-" * len(hdr))
    for t in TRANSFORMS:
        for which in ("pooled", "accepted", "rejected"):
            r = out["arms"][t][which]
            if not r:
                continue
            ci = f"[{r['ci95'][0]:+.4f},{r['ci95'][1]:+.4f}]"
            print(f"{LABEL[t] if which == 'pooled' else '':26s} {which:10s} {r['n']:3d} "
                  f"{r['median']:+8.4f} {ci:>18s} {r['negative']:3d}/{r['positive']:<3d} "
                  f"{r['sign_p']:7.4f} {r['vs_rerun_band']:6.2f} {r['grade_kept']:>7s}")
        print()
    print("the criterion in both of its forms. The pre-registered wording names a MEAN of ABSOLUTE deltas;")
    print("every results table in the paper reports the MEDIAN of the SIGNED delta. Bands: 0.160 median form,")
    print("0.189 mean form, both pre-registered from the same re-run measurement.\n")
    h2 = (f"{'arm':26s} {'n':>3s} {'median D':>9s} {'/0.160':>7s} {'median|D|':>10s} {'/0.160':>7s} "
          f"{'mean|D|':>8s} {'/0.189':>7s} {'passes as written':>18s}")
    print(h2); print("-" * len(h2))
    for t in TRANSFORMS:
        r = out["arms"][t]["pooled"]
        as_written = r["mean_abs"] < BAND_RERUN_MEAN and r["mean_abs"] < BAND_ADJACENT
        print(f"{LABEL[t]:26s} {r['n']:3d} {r['median']:+9.4f} {r['vs_rerun_band']:7.2f} "
              f"{r['median_abs']:10.4f} {r['vs_band_median_abs']:7.2f} {r['mean_abs']:8.4f} "
              f"{r['vs_band_mean_abs']:7.2f} {'yes' if as_written else 'no':>18s}")
    print(f"\nfor scale, the same three statistics on the re-run reference itself, on untouched text:")
    print(f"  median |d| {b['median']:.4f}   mean |d| {b['mean']:.4f}   "
          f"shrunk to this arm's variance: {b['median_matched']:.4f} / {b['mean_matched']:.4f}\n")
    print("what the mean-of-absolute form is actually measuring: spread across papers, against the spread the")
    print("panel has on untouched text. Ratio 1.00 means the arm is exactly as dispersed as re-run noise allows.\n")
    h3 = f"{'arm':26s} {'n':>3s} {'sd delta':>9s} {'sd re-run':>10s} {'ratio':>7s} {'ci95':>16s} {'P(<=1)':>8s}"
    print(h3); print("-" * len(h3))
    for t in TRANSFORMS:
        h = out["arms"][t]["heterogeneity"]
        if not h:
            continue
        ci = f"[{h['ci95'][0]:.2f},{h['ci95'][1]:.2f}]"
        print(f"{LABEL[t]:26s} {h['n']:3d} {h['sd_delta']:9.4f} {h['sd_rerun']:10.4f} "
              f"{h['ratio_to_null']:7.2f} {ci:>16s} {h['share_at_or_below_1']:8.4f}")
    v = out["variant_panel_noise"]
    if len(v) == 3:
        print(f"the assumption that rests on: a panel is no noisier on transformed text than on untouched text.")
        print(f"  per-panel sd, untouched, {v['untouched']['n_pairs']} same-day pairs:   "
              f"{v['untouched']['per_panel_sd']:.4f}")
        print(f"  per-panel sd, transformed, {v['transformed']['n_pairs']} same-day pairs: "
              f"{v['transformed']['per_panel_sd']:.4f}   ratio {v['ratio_transformed_to_untouched']:.2f}")
    print()
    print("does the corpus moderate it?  (two-sample permutation on per-paper deltas)")
    for t, r in out["corpus_test"].items():
        print(f"  {LABEL[t]:26s} accepted - rejected = {r['diff']:+.4f}  p {r['p']:.4f}  "
              f"n {r['n_a']}/{r['n_b']}  {'exact' if r['exact'] else f'{DRAWS} draws'}")
    print("\nis an arm's effect one subgroup?  Three groups, day-matched throughout, so no comparison below")
    print("spans a sitting boundary. Old/new is the pre-scoring rank-interleave rule; exploratory, not a gate.\n")
    h4 = (f"{'arm':26s} {'group':14s} {'n':>3s} {'median':>8s} {'-/+':>7s} {'signp':>7s} {'dose':>6s}")
    print(h4); print("-" * len(h4))
    for t in TRANSFORMS:
        s = out["subgroup_test"].get(t) or {}
        for k, r in (s.get("groups") or {}).items():
            dm = f"{r['dose_median']:6.1f}" if r.get("dose_median") is not None else f"{'--':>6s}"
            print(f"{LABEL[t] if k == 'accepted_old' else '':26s} {k:14s} {r['n']:3d} "
                  f"{r['median']:+8.4f} {r['negative']:3d}/{r['positive']:<3d} {r['sign_p']:7.4f} {dm}")
        for key, what in (("old_vs_new_accepted", "old - new, accepted only"),
                          ("old_vs_everything_else", "old - all other papers")):
            r = s.get(key)
            if r:
                print(f"{'':26s} {what:38s} {r['diff']:+8.4f}  p {r['p']:.4f}  n {r['n_a']}/{r['n_b']}"
                      f"  {'exact' if r['exact'] else f'{DRAWS} draws'}")
        for key, what in (("dose_link", "dose-delta rank correlation, pooled"),
                          ("dose_link_accepted", "  the same, accepted corpus only"),
                          ("dose_link_rejected", "  the same, rejected corpus only")):
            dl2 = out["arms"][t].get(key)
            if dl2:
                print(f"{'':26s} {what:38s} rho {dl2['rho']:+.4f}  p {dl2['p']:.4f}"
                      f"  n {dl2['n']}  median dose {dl2['dose_median']:.1f} "
                      f"(range {dl2['dose_range'][0]}-{dl2['dose_range'][1]})")
        print()
    print("displacement: how many places a variant moves in the untouched reference field. The field is not")
    print("day-centred, so its gaps carry between-sitting variance the transforms cannot cause and every")
    print("displacement below is smaller than a same-day field would give.\n")
    h4 = (f"{'arm':26s} {'n':>3s} {'field':>6s} {'median':>7s} {'mean':>7s} {'worst':>6s} {'best':>5s} "
          f"{'moved':>6s} {'down/up':>8s} {'centred':>8s}")
    print(h4); print("-" * len(h4))
    for t in TRANSFORMS:
        d = out["arms"][t]["displacement"]
        c = out["arms"][t]["displacement_day_centred"]
        if not d:
            continue
        print(f"{LABEL[t]:26s} {d['n']:3d} {d['n_field']:6d} {d['median']:+7.1f} {d['mean']:+7.2f} "
              f"{d['worst']:+6d} {d['best']:+5d} {d['n_moved']:6d} {d['n_down']:4d}/{d['n_up']:<3d} "
              f"{(c['median'] if c else 0):+8.1f}")
    print("\ngrade steps and agreement, one reading against one reading on both sides. The re-run column")
    print("compares the two baseline readings of identical text to each other, over the same cells.\n")
    h4 = (f"{'arm':26s} {'mean |step|':>12s} {'re-run':>8s} {'ratio':>7s} {'agreement':>10s} "
          f"{'re-run':>8s} {'comparisons':>12s}")
    print(h4)
    print("-" * len(h4))
    for t in TRANSFORMS:
        c = out["arms"][t]["grade_cells"]
        if c["mean_step"] is None:
            continue
        print(f"{LABEL[t]:26s} {c['mean_step']:12.4f} {c['mean_step_rerun']:8.4f} "
              f"{c['mean_step'] / c['mean_step_rerun']:7.2f} {c['agreement']:10.4f} "
              f"{c['agreement_rerun']:8.4f} {c['n_comparisons']:12d}")

    print("\ngrade cells. A cell is one reviewer's grade on one paper; it flips only if the variant differs")
    print("from BOTH readings of the untouched text, since differing from one of two is what the instrument")
    print("does to itself. The retest row is that same rate measured on identical text.\n")
    for t in TRANSFORMS:
        c = out["arms"][t]["grade_cells"]
        print(f"  {LABEL[t]:26s} {c['n_flipped']:4d} of {c['n_cells']:4d} cells flip  "
              f"({(c['rate'] or 0):.3f})")
    e = out["grade_cells_any_transform"]
    print(f"  {'under ANY of the three':26s} {e['n_ever_flipped']:4d} of {e['n_cells']:4d} cells "
          f"({(e['rate'] or 0):.3f})")
    print(f"  {'identical text, retest':26s} {e['retest_disagree']:4d} of {e['retest_cells']:4d} cells "
          f"({(e['retest_rate'] or 0):.3f})")
    fn = out["grade_flip_null"]
    if fn["rate"] is not None:
        print(f"\n  the retest row above is one disagreement and the arm rows are a conjunction of two, so")
        print(f"  they are not the same event. The same event with no treatment needs three same-day")
        print(f"  baseline panels, which {fn['n_papers']} of {fn['n_papers'] + fn['n_papers_without']} "
              f"papers have. On those papers alone:")
        print(f"  {'untouched text, same event':26s} {fn['n_flipped']:4d} of {fn['n_comparisons']:4d} "
              f"({fn['rate']:.3f})")
        for t in TRANSFORMS:
            a = fn["arms_on_the_same_papers"][t]
            print(f"  {LABEL[t]:26s} {a['n_flipped']:4d} of {a['n_cells']:4d} "
                  f"({(a['rate'] or 0):.3f})")
        rr = [fn["arms_on_the_same_papers"][t]["rate"] or 0.0 for t in TRANSFORMS]
        print(f"  the arms straddle the reference here, {min(rr):.3f} to {max(rr):.3f} against {fn['rate']:.3f},")
        print(f"  on the cell counts above. So whole-corpus arm rates over {fn['rate']:.3f} are a difference")
        print(f"  of population, and the conjunctive comparison is not available at this corpus size. The")
        print(f"  step and agreement table above is the one that is.\n")
    rm = out.get("roster_matched")
    if rm and rm["arms"]:
        print(f"\nthe two rosters on ONE paper set. The eight-slot roster covers {len(rm['papers'])} papers and")
        print(f"this one covers every paper above, so a difference between the two published readings is a")
        print(f"difference of instrument and of paper set at once. Restricted to the eight the other roster")
        print(f"scored, each side over its own PRE-REGISTERED band ({BAND_RERUN:.3f} and "
              f"{rm['eight_slot_band']:.4f}). The band")
        print(f"measured on these eight alone is {rm['five_slot_band']['median']:.4f} for this roster, which is "
              f"eight single gaps and")
        print(f"is not used as a denominator anywhere:\n")
        h = f"{'arm':26s} {'five slot':>10s} {'/band':>7s} {'eight slot':>11s} {'/band':>7s} {'same sign':>10s}"
        print(h)
        print("-" * len(h))
        for t in TRANSFORMS:
            a = rm["arms"].get(t)
            if not a:
                continue
            print(f"{LABEL[t]:26s} {a['five_slot']['median']:10.4f} {a['five_slot_vs_own_band']:7.2f} "
                  f"{a['eight_slot']['median']:11.4f} {a['eight_slot_vs_own_band']:7.2f} "
                  f"{('yes' if a['same_sign'] else 'NO'):>10s}")
        print(f"\n{'arm':26s} {'grade 5':>10s} {'/rerun':>7s} {'grade 8':>11s} {'/rerun':>7s}")
        for t in TRANSFORMS:
            a = rm["arms"].get(t)
            if not a:
                continue
            print(f"{LABEL[t]:26s} {a['five_slot_grade']['mean_step']:10.4f} "
                  f"{a['five_slot_grade_ratio']:7.2f} {a['eight_slot_grade']['mean_step']:11.4f} "
                  f"{a['eight_slot_grade_ratio']:7.2f}")
        ao = rm.get("arm_ordering") or {}
        if ao:
            print(f"\n  which presentation arm costs more, PAIRED within paper. Two medians measured against")
            print(f"  two baselines is not a test of the difference between them, and read that way this")
            print(f"  comparison gave both answers:\n")
            print(f"  {'reading':52s} {'n':>3s} {'T3-T1':>8s} {'sign':>7s} {'p':>8s}")
            for k, v in ao.items():
                if not isinstance(v, dict):
                    continue
                p = v.get("p_sign_test", v.get("p_vs_rerun_null"))
                print(f"  {v['reading']:52s} {v['n']:3d} {v['delta']:8.4f} "
                      f"{f'{v['sign'][0]}-/{v['sign'][1]}+':>7s} {p:8.4f}"
                      f"  -> {LABEL[v['larger']]} larger")
            print(f"\n  the same arm is larger everywhere: "
                  f"{'yes' if ao.get('same_arm_larger_everywhere') else 'NO'}"
                  f"; separable on eight papers: "
                  f"{'yes' if ao.get('separable_on_eight_papers') else 'NO'}"
                  f"; on the full corpus: "
                  f"{'yes' if ao.get('separable_on_full_corpus') else 'NO'}")
            print(f"  So the two rosters do not disagree about the ordering. Neither resolves it on eight")
            print(f"  papers, and the reading that resolves it has forty-six.")
        print()
    print(f"  {'flipped under all three':26s} {e['flipped_under_all_three']:4d}")
    for t in TRANSFORMS:
        print(f"    of {LABEL[t]}'s flips, shared with another arm: "
              f"{e['shared_with_another_arm'][t]:3d} ({(e['shared_share'][t] or 0):.3f})")
    print()
    json.dump(out, open(f"{AN}/pooled_analysis.json", "w"), indent=1)
    print(f"\nwrote pooled_analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

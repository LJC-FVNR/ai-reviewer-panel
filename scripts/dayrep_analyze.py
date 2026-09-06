#!/usr/bin/env python3
"""Does a presentation effect survive a change of sitting? The eight papers that carry T1's, re-read.

WHAT THIS ANSWERS. Under the day-matched contrast T1's whole effect sits in eight of the sixteen accepted
papers, and those eight are exactly the papers whose T1 and T3 variants were scored on 2026-08-31 while every
other paper's were scored on 2026-09-01. The subset label and the sitting label name one partition, in this arm
and in every other arm of this roster, so a property of the manuscripts and a property of the sitting predict
the same table. Several measurements narrow that confound and none of them closes it, which is why this arm
exists.

N1d scores those same eight variant texts, byte-for-byte unchanged, in a later sitting, with two fresh baseline
panels per paper in that same sitting. So each paper contributes two readings of one text: the original, taken
against baselines from its own earlier sitting, and the replication, taken against baselines from the later one.
Both are within-paper and within-sitting; the difference between them is the sitting.

HOW IT IS READ, and this was fixed before the arm ran. T3 is the internal
positive control and is read first, because it decides whether the T1 answer means anything:

  * T3 clearly negative in the later sitting  -> the sitting can register a presentation cost, so a T1 reading
    in it is interpretable.
  * T3 collapsed as well                      -> the later sitting differs in kind from the earlier one and
    neither transform's reading in it is evidence about the other. The arm is reported as uninformative rather
    than mined for whichever half agrees with something.

Then, conditional on the first branch, T1 near its original value means the effect belongs to these eight
papers, and T1 near zero means the original reading did not survive a second sitting. Either way the pooled
forty-eight-paper median stays what section 6 reports: eight papers selected because they disagree with the
other forty are a diagnostic, not a sample.

The baselines are the arm's second product. They are a fresh measurement of the same untouched text these
papers were read on in the earlier sitting, so they re-measure the day offset that made the day-matched contrast
primary in the first place -- on the same eight papers, with the earlier sitting's own pair still on disk.

    python3 dayrep_analyze.py [--json]
"""
from __future__ import annotations

import collections
import json
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pooled_analyze import (DRAWS, SEED, load, matched_pairs, modal, modal_over, perm2, same_day_pair,
                            sign_p)

AN = os.path.dirname(os.path.abspath(__file__))
TRANSFORMS = ("T3_lengthen", "T1_endmatter")   # positive control first, deliberately
LABEL = {"T1_endmatter": "T1 figures -> end matter", "T3_lengthen": "T3 join sentences"}
ORIGINAL_DAY = "2026-08-31"


def by_source(rows, tag):
    """-> {paper: {condition: {panel: row}}} for one arm of the reading table."""
    out = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in rows:
        src, _, pn = r["panel"].partition("/")
        if src == tag:
            out[r["paper"]][r["condition"]][pn] = r
    return out


def one_sitting(conds, transform, day=None):
    """-> (delta, variant row, baseline pair) for a transform inside a single sitting, or None.

    The variant is that arm's single variant panel and the baseline is the mean of the two baseline panels from
    the variant's own day, which is `same_day_pair`'s rule -- the same one the pooled analysis uses, imported
    rather than restated so the two arms are differenced the same way.
    """
    var = (conds.get(transform) or {}).get("panel1")
    if not var:
        return None
    if day and var["day"] != day:
        return None
    pair = same_day_pair(conds.get("baseline") or {}, var["day"])
    if not pair:
        return None
    return var["z"] - st.mean(b["z"] for b in pair), var, pair


def paired_perm(d, rng):
    """Exact sign-flip permutation on a paired difference. Eight papers is 256 sign patterns, so exact."""
    import itertools
    import numpy as np
    a = np.asarray(d, float)
    obs = float(np.median(a))
    stats = [float(np.median(a * np.asarray(s, float)))
             for s in itertools.product((1.0, -1.0), repeat=len(a))]
    ge = sum(1 for x in stats if abs(x) >= abs(obs) - 1e-12)
    return {"median": round(obs, 4), "p": round(ge / len(stats), 4), "n_patterns": len(stats)}


def boot_med(d, rng):
    import numpy as np
    a = np.asarray(d, float)
    m = np.median(a[rng.integers(0, len(a), size=(DRAWS, len(a)))], axis=1)
    return [round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def arm_ordering(out, rng):
    """-> the paired difference between the two presentation arms, in each of the two sittings.

    Two arms each measured against its own baseline, with one median larger than the other, is not a finding
    about which arm is larger; the difference has to be taken within paper and tested. Here it can be taken
    twice on the same texts and the same roster -- once in the sitting the arms were built in, once in the
    later sitting -- which is the only place in the study where the ordering can be asked of one instrument
    rather than of two. The paper currently attributes that ordering to the panel, on the strength of a
    comparison between two rosters that cover different sets of papers.

    The sign convention follows the arm order declared above: negative means the first arm named is larger.
    """
    T = [t for t in TRANSFORMS if (out["arms"].get(t) or {}).get("per_paper")]
    if len(T) != 2:
        return None
    a, b = T
    pa, pb = out["arms"][a]["per_paper"], out["arms"][b]["per_paper"]
    shared = sorted(set(pa) & set(pb))
    if len(shared) < 4:
        return {"withheld": "fewer than four papers carry both arms"}
    res = {"pair": [a, b], "n": len(shared),
           "sign_convention": f"negative means {LABEL[a]} is the larger arm"}
    for when in ("original", "later"):
        d = [pa[p][when] - pb[p][when] for p in shared]
        r = paired_perm(d, rng)
        res[when] = {"median": r["median"], "ci95": boot_med(d, rng), "p": r["p"],
                     "n_patterns": r["n_patterns"],
                     "larger": a if r["median"] < 0 else b,
                     "negative": sum(1 for x in d if x < 0)}
    res["same_arm_larger_in_both"] = res["original"]["larger"] == res["later"]["larger"]
    # An ordering counts as resolved by this roster only when one arm is larger in both sittings AND the
    # difference is distinguishable in both. Either half can fail, and they fail for different reasons, so
    # both are recorded rather than collapsed into the flag.
    res["resolved_by_this_roster"] = bool(res["same_arm_larger_in_both"]
                                         and res["original"]["p"] < 0.05 and res["later"]["p"] < 0.05)
    return res


def same_sitting_contrast(rows, out, rng):
    """The eight papers against every other paper, both read in the later sitting.

    This is the only contrast in the study in which the subset and the sitting are not the same variable. The
    eight contribute their N1d reading, taken against N1d's own baselines from that sitting; the others
    contribute the day-matched reading section 6 reports, restricted to the same day. Both sides are therefore
    within-paper and within-sitting, and the only thing that differs across the two groups is which papers
    they are.
    """
    res = {}
    for t in TRANSFORMS:
        arm = out["arms"].get(t) or {}
        pp = arm.get("per_paper") or {}
        if not pp:
            continue
        days = {v["later_day"] for v in pp.values()}
        if len(days) != 1:
            res[t] = {"withheld": "the replication readings do not share one day"}
            continue
        day = days.pop()
        eight = [v["later"] for v in pp.values()]
        others = [p["delta"] for p in matched_pairs(rows, t)
                  if p["day"] == day and p["paper"] not in pp]
        if len(eight) < 4 or len(others) < 4:
            res[t] = {"withheld": "too few papers on one side"}
            continue
        r = perm2(eight, others, rng)
        res[t] = {"day": day, "n_eight": len(eight), "n_others": len(others),
                  "median_eight": round(st.median(eight), 4), "median_others": round(st.median(others), 4),
                  "diff": r.get("diff"), "p": r.get("p")}
    return res


def main():
    import numpy as np
    rng = np.random.default_rng(SEED)
    rows = load()      # the shared loader, so the incomplete-panel filter is not restated here
    new, orig = by_source(rows, "n1d"), by_source(rows, "n1b")
    if not new:
        print("no N1d readings on disk yet; nothing to analyse")
        return 0

    out = {"n_papers_scored": len(new), "arms": {}, "day_offset_replication": None}

    # ---- the untouched-text day offset, re-measured on these same eight papers -----------------------
    off, spread_new, spread_old = [], [], []
    for pid, conds in sorted(new.items()):
        a = same_day_pair(conds.get("baseline") or {})
        b = same_day_pair((orig.get(pid) or {}).get("baseline") or {}, ORIGINAL_DAY)
        if a and b:
            off.append(st.mean(x["z"] for x in a) - st.mean(x["z"] for x in b))
            spread_new.append(abs(a[0]["z"] - a[1]["z"]))
            spread_old.append(abs(b[0]["z"] - b[1]["z"]))
    if len(off) >= 4:
        out["day_offset_replication"] = {
            "n": len(off), "median": round(st.median(off), 4), "mean": round(st.mean(off), 4),
            "ci95": boot_med(off, rng), "negative": sum(1 for x in off if x < 0),
            "sign_p": sign_p(off),
            "rerun_spread_later": round(st.median(spread_new), 4),
            "rerun_spread_original": round(st.median(spread_old), 4)}

    # ---- the two readings of each transform ---------------------------------------------------------
    for t in TRANSFORMS:
        per = {}
        for pid, conds in sorted(new.items()):
            a = one_sitting(conds, t)
            b = one_sitting((orig.get(pid) or {}), t, ORIGINAL_DAY)
            if a and b:
                per[pid] = {"later": round(a[0], 4), "original": round(b[0], 4),
                            "shift": round(a[0] - b[0], 4), "later_day": a[1]["day"],
                            "grade_later": modal(a[1]["grades"]), "grade_base_later": modal_over(a[2])}
        if len(per) < 4:
            out["arms"][t] = {"n": len(per), "per_paper": per}
            continue
        L = [v["later"] for v in per.values()]
        O = [v["original"] for v in per.values()]
        S = [v["shift"] for v in per.values()]
        kept = [v for v in per.values() if v["grade_later"] and v["grade_base_later"]]
        out["arms"][t] = {
            "n": len(per),
            "later": {"median": round(st.median(L), 4), "ci95": boot_med(L, rng),
                      "negative": sum(1 for x in L if x < 0), "sign_p": sign_p(L)},
            "original": {"median": round(st.median(O), 4), "ci95": boot_med(O, rng),
                         "negative": sum(1 for x in O if x < 0), "sign_p": sign_p(O)},
            "shift": paired_perm(S, rng),
            "grade_kept": f"{sum(1 for v in kept if v['grade_later'] == v['grade_base_later'])}/{len(kept)}",
            "per_paper": per}

    if "--json" in sys.argv:
        json.dump(out, sys.stdout, indent=1)
        return 0

    print(f"N1d: {out['n_papers_scored']} of 8 papers have readings on disk\n")
    d = out["day_offset_replication"]
    if d:
        print("THE DAY OFFSET, RE-MEASURED ON UNTOUCHED TEXT")
        print(f"  same eight papers, byte-identical baselines, later sitting minus {ORIGINAL_DAY}:")
        print(f"  median {d['median']:+.4f} z   ci95 [{d['ci95'][0]:+.4f},{d['ci95'][1]:+.4f}]   "
              f"{d['negative']}/{d['n']} negative   sign p {d['sign_p']:.4f}")
        print(f"  re-run spread within the sitting: {d['rerun_spread_original']:.4f} then "
              f"{d['rerun_spread_later']:.4f}\n")

    print("THE TWO READINGS OF EACH TRANSFORM. T3 is the positive control and is read first.\n")
    h = (f"{'arm':26s} {'n':>3s} {'original':>9s} {'later':>9s} {'ci95 later':>19s} {'-/+ later':>10s} "
         f"{'shift':>8s} {'p':>7s} {'grade':>6s}")
    print(h); print("-" * len(h))
    for t in TRANSFORMS:
        r = out["arms"].get(t) or {}
        if "later" not in r:
            print(f"{LABEL[t]:26s} {r.get('n', 0):3d}   (too few papers scored to read)")
            continue
        ci = f"[{r['later']['ci95'][0]:+.4f},{r['later']['ci95'][1]:+.4f}]"
        print(f"{LABEL[t]:26s} {r['n']:3d} {r['original']['median']:+9.4f} {r['later']['median']:+9.4f} "
              f"{ci:>19s} {r['later']['negative']:4d}/{r['n'] - r['later']['negative']:<5d} "
              f"{r['shift']['median']:+8.4f} {r['shift']['p']:7.4f} {r['grade_kept']:>6s}")
    print("\nper paper, both readings of the same text:")
    for t in TRANSFORMS:
        r = out["arms"].get(t) or {}
        if not r.get("per_paper"):
            continue
        print(f"  {LABEL[t]}")
        for pid, v in sorted(r["per_paper"].items(), key=lambda kv: kv[1]["original"]):
            print(f"    {pid:12s} original {v['original']:+.4f}   later {v['later']:+.4f}   "
                  f"shift {v['shift']:+.4f}   ({v['later_day']})")
    # perm2 permutes with a numpy generator, so it gets one; SEED is the study's single seed.
    import numpy as np
    out["same_sitting_contrast"] = same_sitting_contrast(rows, out, np.random.default_rng(SEED))
    out["arm_ordering"] = arm_ordering(out, np.random.default_rng(SEED))
    ao = out["arm_ordering"] or {}
    if "original" in ao:
        print(f"\nwhich presentation arm is larger, paired within paper over {ao['n']} papers "
              f"({ao['sign_convention']}):")
        for when in ("original", "later"):
            w = ao[when]
            print(f"  {when:9s} {w['median']:+.4f}  ci95 [{w['ci95'][0]:+.4f}, {w['ci95'][1]:+.4f}]  "
                  f"p {w['p']:.4f} over {w['n_patterns']} sign patterns  "
                  f"{w['negative']}/{ao['n']} negative  -> {LABEL[w['larger']]}")
        print(f"  same arm larger in both sittings: {ao['same_arm_larger_in_both']}; "
              f"ordering resolved by this roster: {ao['resolved_by_this_roster']}")
    print("\nTHE SUBSET AGAINST THE OTHERS, SITTING HELD FIXED")
    print("  the one contrast in which the subset label and the sitting label are different variables:")
    for t in TRANSFORMS:
        c = out["same_sitting_contrast"].get(t)
        if not c:
            continue
        if "withheld" in c:
            print(f"  {LABEL[t]:26s} withheld -- {c['withheld']}")
            continue
        print(f"  {LABEL[t]:26s} the {c['n_eight']} {c['median_eight']:+.4f} vs the other "
              f"{c['n_others']} {c['median_others']:+.4f} on {c['day']}, "
              f"difference {c['diff']:+.4f}, p {c['p']:.4f}")

    json.dump(out, open(f"{AN}/dayrep_analysis.json", "w"), indent=1)
    print("\nwrote dayrep_analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

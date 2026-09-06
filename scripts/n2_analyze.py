#!/usr/bin/env python3
"""N2 -- the presentation-invariance audit re-run on a roster sharing no vendor with the panel of section 6.

WHAT THIS ANSWERS. Section 6 measures three mechanical edits on the five-model panel. The reading a venue
would act on is "use several vendors and the effect washes out". That is a claim about a different panel, so no
amount of extra data on the first one settles it. The rule was fixed before the queue ran: a same-signed
delta on both rosters means vendor diversity is NOT a defence and the recommendation is struck from
section 9; a delta that vanishes makes it a partial mitigation, stated as one.

WHAT IS COMPARABLE ACROSS THE TWO ROSTERS, AND WHAT IS NOT.
  comparable      the SIGN of each transform's delta -- per paper, and per slot -- and the delta expressed in
                  multiples of the roster's OWN test-retest band. Eight slots average more reviews than five,
                  so the second roster is quieter: its band is 0.060 z against the five-model panel's 0.160 z.
  not comparable  raw |delta z| between rosters. A quieter instrument reports a genuine effect as a smaller
                  number, so a raw comparison would credit averaging with robustness it has not got.

THE TWO SIDES OF THE DELTA ARE NOT SYMMETRIC IN PANEL COUNT, which is stated rather than hidden. Every
baseline is N0's two panels (16 reviews); every variant is one panel (8 reviews), because a second variant
panel would have doubled a queue this arm did not need. With single-panel variance s2 a delta carries 1.5*s2
while the band |p1-p2| carries 2*s2, so a delta is slightly QUIETER than the band it is compared against and
"the delta exceeds the band" is a conservative test rather than a flattering one. Section 6's five-model arm
scored two variant panels, where the same ratio is 1.0 against 2.0.

FROZEN INSTRUMENT. Variants are standardised with the mu and sigma already fitted on the untransformed 16
papers. Refitting on the variants would let the treatment move the yardstick measuring it.

QUEUE POSITION IS CHECKED, NOT ASSUMED. The 24 jobs were shuffled with a fixed seed so that condition could
not be confounded with position in a queue that drains over tens of minutes. This script reproduces that
shuffle and reports the balance it achieved, plus the correlation between position and delta.

THE DRIFT CONTROL. Both arms difference a variant scored in one session against a baseline scored in an
earlier one, so a level shift in the provider between sessions lands inside the delta and looks exactly like a
treatment: a common negative offset across all three transforms is what it would produce. run_n3.sh therefore
re-scores the untouched baseline text -- sha256-identical to what N0 read -- on the same roster in the same
session as the variants, which is the only text whose true effect is known to be zero. Where that tree exists
this script reports the offset and the corrected deltas, and applies the pre-registered rule to the corrected
numbers. The common offset is subtracted, not the per-paper one: the control is a single panel, so per-paper
subtraction would inject its noise into every delta to remove a shift that is by hypothesis shared. The paired
form is reported beside it as a robustness line.

  python3 n2_analyze.py [--json]
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
N0 = f"{AN}/n0_cursor8_iclr"
N2 = f"{AN}/n2_pia_cursor8"
PARAMS = f"{N0}/calibration_params_cursor8_iclr.json"
MODELS = "/path/to/workspace/paper_direction_72/cursor_panel/panel_models.json"
N1 = f"{AN}/n1_results.json"
VARIANTS = ["T1_endmatter", "T2_concede", "T3_lengthen"]
SHORT = {"T1_endmatter": "T1", "T2_concede": "T2", "T3_lengthen": "T3"}
GRADES = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]
LEVEL = {g: i for i, g in enumerate(GRADES)}


def jload(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def score(r, metric):
    """-> float score, or None. cursor8 writes scores as strings and the five-model runner writes ints; both
    mean the same integer, so the coercion is where that difference is allowed to stop mattering."""
    v = (r.get("metrics") or {}).get(metric)
    if isinstance(v, dict):
        v = v.get("score")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def zmean(r, slot, mu, sd, metrics):
    z = []
    for m in metrics:
        s = score(r, m)
        k = f"{slot}|{m}"
        if s is not None and sd.get(k):
            z.append((s - mu[k]) / sd[k])
    return st.mean(z) if z else None


def grade_of(r):
    return r.get("grade") or r.get("overall_grade")


def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            for k in range(i, j + 1):
                out[s[k]] = (i + j) / 2 + 1
            i = j + 1
        return out
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def boot_median(vals, n=10000, seed=20260830):
    rng = random.Random(seed)
    meds = sorted(st.median(rng.choices(vals, k=len(vals))) for _ in range(n))
    return [round(meds[int(0.025 * n)], 4), round(meds[int(0.975 * n)], 4)]


def sign_p(neg, tot):
    """Two-sided exact binomial p at p=0.5 -- the sign test on 8 papers, which is the whole inferential
    claim available at n=8. Reported so nobody has to take '8 of 8' on trust."""
    k = max(neg, tot - neg)
    tail = sum(math.comb(tot, i) for i in range(k, tot + 1)) / 2 ** tot
    return round(min(1.0, 2 * tail), 4)


def queue_order():
    """Reproduce run_n2.sh's fixed-seed shuffle: papers in glob (lexicographic) order, transforms in the
    script's VARIANTS order, then Random(20260830).shuffle. Recomputed rather than read off file times, so the
    design's balance can be checked without trusting a filesystem clock."""
    papers = sorted(os.path.basename(d.rstrip("/")) for d in glob.glob(f"{AN}/pia_variants/*/"))
    jobs = [f"{p}/{v}" for p in papers for v in VARIANTS]
    jobs = [j for j in jobs if os.path.isdir(f"{N2}/reviews/{j}/panel1")]
    random.Random(20260830).shuffle(jobs)
    return {j: i for i, j in enumerate(jobs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="print the result object instead of the report")
    a = ap.parse_args()

    par = jload(PARAMS)
    mu, sd, metrics = par["mu"], par["sd"], par["metrics"]
    band = par["test_retest_noise"]["median_abs_between_panel_composite_gap"]
    slots = [s["slot"] for s in jload(MODELS)["panel"]]
    disp = {s["slot"]: s.get("display") or s.get("model") for s in jload(MODELS)["panel"]}
    vendor = {s["slot"]: s.get("vendor", "?") for s in jload(MODELS)["panel"]}

    # --- baselines: this roster's own N0 reviews, per (paper, panel, slot) --------------------------------
    base: dict[str, dict[str, dict[str, float]]] = {}
    bgrade: dict[tuple[str, str], list[str]] = {}
    for f in sorted(glob.glob(f"{N0}/reviews/*/panel*/C?.json")):
        if os.path.getsize(f) <= 2:
            continue
        paper, panel, slot = f.split("/")[-3], f.split("/")[-2], os.path.basename(f)[:2]
        r = jload(f)
        v = zmean(r, slot, mu, sd, metrics)
        if v is not None:
            base.setdefault(paper, {}).setdefault(panel, {})[slot] = v
        bgrade.setdefault((paper, slot), []).append(grade_of(r))

    # --- variants: one panel each ------------------------------------------------------------------------
    var: dict[tuple[str, str], dict[str, float]] = {}
    vgrade: dict[tuple[str, str, str], str] = {}
    for f in sorted(glob.glob(f"{N2}/reviews/*/*/panel1/C?.json")):
        if os.path.getsize(f) <= 2:
            continue
        paper, variant, slot = f.split("/")[-4], f.split("/")[-3], os.path.basename(f)[:2]
        r = jload(f)
        v = zmean(r, slot, mu, sd, metrics)
        if v is not None:
            var.setdefault((paper, variant), {})[slot] = v
        vgrade[(paper, variant, slot)] = grade_of(r)

    papers = sorted({p for p, _ in var})
    holes = [(p, v, s) for p in papers for v in VARIANTS for s in slots
             if s not in var.get((p, v), {})]
    missing_base = [p for p in papers if p not in base or len(base[p]) < 2]
    if holes or missing_base:
        # A hole is not neutral: a variant missing the slot its baseline has turns that paper's delta into a
        # comparison between two different rosters, which is the one thing this arm exists to avoid.
        print(f"REFUSING to report: {len(holes)} missing variant reviews, "
              f"{len(missing_base)} papers without a two-panel baseline")
        for p, v, s in holes[:10]:
            print(f"  missing {p}/{v}/{s}")
        return 2

    res: dict = {
        "instrument": os.path.basename(PARAMS) + " (frozen; not refit on variants)",
        "n_variant_reviews": len(vgrade),
        "n_papers": len(papers),
        "n_slots": len(slots),
        "rerun_band_this_roster": band,
        "panels": {"baseline": 2, "variant": 1},
        "holes": 0,
    }

    # --- paper-level deltas ------------------------------------------------------------------------------
    bcomp = {p: st.mean(st.mean(d.values()) for d in base[p].values()) for p in papers}
    res["transforms"] = {}
    for v in VARIANTS:
        d = {p: st.mean(var[(p, v)].values()) - bcomp[p] for p in papers}
        vals = [d[p] for p in papers]
        neg = sum(1 for x in vals if x < 0)
        res["transforms"][v] = {
            "median_delta": round(st.median(vals), 4),
            "median_abs_delta": round(st.median([abs(x) for x in vals]), 4),
            "mean_delta": round(st.mean(vals), 4),
            "delta_ci95": boot_median(vals),
            "n_negative": neg,
            "n_positive": len(vals) - neg,
            "sign_test_p": sign_p(neg, len(vals)),
            # The only cross-roster-legal normalisation: each roster's movement in units of its own noise.
            "abs_delta_over_own_band": round(abs(st.median(vals)) / band, 3),
            "per_paper": {p: round(d[p], 4) for p in papers},
        }

    # --- per-slot deltas: does any single vendor escape the effect? --------------------------------------
    # This is the sharpest form of the vendor question. A venue cannot buy its way out of a sensitivity that
    # every slot on a six-vendor roster shows on its own reviews.
    for v in VARIANTS:
        rows = {}
        for s in slots:
            per = [var[(p, v)][s] - st.mean(base[p][k][s] for k in base[p]) for p in papers]
            rows[s] = {"vendor": vendor[s], "display": disp[s],
                       "median_delta": round(st.median(per), 4),
                       "n_negative": sum(1 for x in per if x < 0)}
        res["transforms"][v]["per_slot"] = rows
        res["transforms"][v]["slots_negative"] = sum(1 for s in rows if rows[s]["median_delta"] < 0)

    # --- the grade channel, against this roster's own re-run agreement -----------------------------------
    cell_same = [1 if len(set(g)) == 1 else 0 for g in bgrade.values() if len(g) == 2]
    res["grade_retest_this_roster"] = {
        "n_cells": len(cell_same), "agreement": round(st.mean(cell_same), 4),
        "mean_abs_step": round(st.mean([abs(LEVEL[g[0]] - LEVEL[g[1]]) for g in bgrade.values()
                                       if len(g) == 2 and all(x in LEVEL for x in g)]), 4),
    }
    for v in VARIANTS:
        moved, steps, modal_kept = 0, [], 0
        for p in papers:
            bl = [LEVEL[g] for s in slots for g in bgrade[(p, s)] if g in LEVEL]
            vl = [LEVEL[vgrade[(p, v, s)]] for s in slots if vgrade[(p, v, s)] in LEVEL]
            for s in slots:
                gv = vgrade[(p, v, s)]
                gb = bgrade[(p, s)]
                if gv not in gb:
                    moved += 1
                if gv in LEVEL and all(x in LEVEL for x in gb):
                    steps.append(abs(LEVEL[gv] - st.mean(LEVEL[x] for x in gb)))
            if vl and bl and st.mode(vl) == st.mode(bl):
                modal_kept += 1
        res["transforms"][v]["grade"] = {
            "cells_moved_off_baseline": moved, "n_cells": len(papers) * len(slots),
            "mean_abs_step": round(st.mean(steps), 4),
            "modal_grade_kept": modal_kept, "n_papers": len(papers),
        }

    # --- queue balance and drift -------------------------------------------------------------------------
    qi = queue_order()
    if len(qi) == len(papers) * len(VARIANTS):
        pos = {v: [qi[f"{p}/{v}"] for p in papers] for v in VARIANTS}
        res["queue"] = {
            "n_jobs": len(qi),
            "mean_position_by_transform": {SHORT[v]: round(st.mean(pos[v]), 2) for v in VARIANTS},
            "expected_mean_position": (len(qi) - 1) / 2,
        }
        allj = [(qi[f"{p}/{v}"], st.mean(var[(p, v)].values()) - bcomp[p]) for p in papers for v in VARIANTS]
        allj.sort()
        half = len(allj) // 2
        res["queue"]["rho_position_vs_delta"] = round(spearman([x for x, _ in allj], [y for _, y in allj]), 4)
        res["queue"]["later_minus_earlier_mean_delta"] = round(
            st.mean([y for _, y in allj[half:]]) - st.mean([y for _, y in allj[:half]]), 4)
    else:
        res["queue"] = {"n_jobs": len(qi), "note": "shuffle not reproducible from pia_variants/; skipped"}

    # --- the drift control: byte-identical text, same roster, same session as the variants ---------------
    n3 = f"{AN}/n3_drift_cursor8/reviews"
    ctrl = {}
    for f in sorted(glob.glob(f"{n3}/*/panel1/C?.json")):
        if os.path.getsize(f) <= 2:
            continue
        paper, slot = f.split("/")[-3], os.path.basename(f)[:2]
        v = zmean(jload(f), slot, mu, sd, metrics)
        if v is not None:
            ctrl.setdefault(paper, {})[slot] = v
    full = [p for p in papers if len(ctrl.get(p, {})) == len(slots)]
    if len(full) == len(papers):
        dr = {p: st.mean(ctrl[p].values()) - bcomp[p] for p in papers}
        drift = st.median(dr.values())
        res["drift_control"] = {
            "n_reviews": sum(len(ctrl[p]) for p in papers), "n_papers": len(papers),
            "text": "pia_variants/<id>/baseline.txt, sha256-identical to the text N0 scored",
            "median_offset": round(drift, 4), "offset_ci95": boot_median(list(dr.values())),
            "n_negative": sum(1 for x in dr.values() if x < 0),
            "offset_over_own_band": round(abs(drift) / band, 3),
            "per_paper": {p: round(dr[p], 4) for p in papers},
        }
        for v in VARIANTS:
            t = res["transforms"][v]
            raw = [t["per_paper"][p] for p in papers]
            corr = [x - drift for x in raw]
            paired = [t["per_paper"][p] - dr[p] for p in papers]
            neg = sum(1 for x in corr if x < 0)
            t["corrected"] = {
                "median_delta": round(st.median(corr), 4),
                "delta_ci95": boot_median(corr),
                "n_negative": neg, "n_positive": len(corr) - neg,
                "sign_test_p": sign_p(neg, len(corr)),
                "abs_delta_over_own_band": round(abs(st.median(corr)) / band, 3),
                "paired_median_delta": round(st.median(paired), 4),
                "paired_n_negative": sum(1 for x in paired if x < 0),
            }
    elif ctrl:
        res["drift_control"] = {"note": f"incomplete: {len(full)}/{len(papers)} papers have all "
                                        f"{len(slots)} slots; not used", "n_papers_complete": len(full)}

    # --- the five-model arm, read from its own results file rather than transcribed ----------------------
    n1 = jload(N1)
    res["five_model"] = {
        "rerun_band": n1["test_retest_band_median"],
        "transforms": {v: {"median_delta": n1["transforms"][v]["median_delta"],
                           "n_negative": n1["transforms"][v]["n_negative"],
                           "abs_delta_over_own_band": round(abs(n1["transforms"][v]["median_delta"])
                                                            / n1["test_retest_band_median"], 3)}
                       for v in VARIANTS},
    }

    # --- the pre-registered verdict ---------------------------------------------------------------------
    # T2 is excluded from the presentation reading in section 6 and stays excluded here: its substitution
    # table withdraws a claim of statistical significance, so a reviewer marking it down may be correct.
    pia = ["T1_endmatter", "T3_lengthen"]
    # Where the drift control ran, the rule is applied to the corrected delta: the uncorrected one contains a
    # between-session offset that is not the treatment, and reporting the flattering version of a
    # pre-registered test is the failure mode pre-registration exists to prevent.
    def dec(v):
        return res["transforms"][v].get("corrected", res["transforms"][v])
    same_sign = {v: (dec(v)["median_delta"] < 0) == (n1["transforms"][v]["median_delta"] < 0) for v in pia}
    survives = {v: dec(v)["abs_delta_over_own_band"] >= 1.0 for v in pia}
    res["verdict"] = {
        "applied_to": "drift-corrected delta" if "corrected" in res["transforms"][pia[0]] else "raw delta",
        "same_sign_both_rosters": same_sign,
        "exceeds_own_rerun_band": survives,
        "vendor_diversity_is_a_defence": not (all(same_sign.values()) and all(survives.values())),
        "rule": ("Fixed before the run: same-signed delta on both rosters and above each "
                 "roster's own band => vendor diversity is not a defence and the recommendation is struck "
                 "from section 9; a delta that vanishes on the wider roster => partial mitigation, said so."),
    }

    os.makedirs(N2, exist_ok=True)
    with open(f"{N2}/n2_analysis.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, sort_keys=False)

    if a.json:
        print(json.dumps(res, indent=2))
        return 0

    p = print
    p(f"N2 -- presentation invariance on the eight-slot, six-vendor roster")
    p(f"  {res['n_variant_reviews']} variant reviews, {res['n_papers']} papers x {len(VARIANTS)} transforms "
      f"x {res['n_slots']} slots, 0 holes")
    p(f"  instrument frozen: {res['instrument']}")
    p(f"  this roster's own re-run band: {band} z   (five-model panel: {n1['test_retest_band_median']} z)")
    p("")
    p(f"  {'transform':<14} {'median dz':>10} {'95% CI':>20} {'sign':>8} {'p':>7} "
      f"{'/own band':>10} {'slots neg':>10}")
    for v in VARIANTS:
        t = res["transforms"][v]
        p(f"  {SHORT[v]} {v.split('_')[1]:<11} {t['median_delta']:>+10.3f} "
          f"{str(t['delta_ci95']):>20} {str(t['n_negative']) + '- / ' + str(t['n_positive']) + '+':>8} "
          f"{t['sign_test_p']:>7} {t['abs_delta_over_own_band']:>10.2f}x {t['slots_negative']:>9}/8")
    p("")
    p("  the same transforms on the five-model panel, each in units of its own band:")
    for v in VARIANTS:
        f5, f2 = res["five_model"]["transforms"][v], res["transforms"][v]
        p(f"    {SHORT[v]}  five-model {f5['median_delta']:+.3f} ({f5['abs_delta_over_own_band']:.2f}x, "
          f"{f5['n_negative']}-/8)   cursor8 {f2['median_delta']:+.3f} "
          f"({f2['abs_delta_over_own_band']:.2f}x, {f2['n_negative']}-/8)")
    p("")
    if "median_offset" in res.get("drift_control", {}):
        c = res["drift_control"]
        p(f"  drift control: {c['n_reviews']} reviews of byte-identical text, same session as the variants")
        p(f"    offset {c['median_offset']:+.4f} z (CI {c['offset_ci95']}, {c['n_negative']}-/8, "
          f"{c['offset_over_own_band']:.2f}x this roster's band) -- the treatment-free level shift")
        p(f"  {'transform':<14} {'corrected dz':>13} {'95% CI':>20} {'sign':>8} {'/own band':>10} {'paired':>9}")
        for v in VARIANTS:
            c2 = res["transforms"][v]["corrected"]
            p(f"  {SHORT[v]} {v.split('_')[1]:<11} {c2['median_delta']:>+13.3f} {str(c2['delta_ci95']):>20} "
              f"{str(c2['n_negative']) + '- / ' + str(c2['n_positive']) + '+':>8} "
              f"{c2['abs_delta_over_own_band']:>10.2f}x {c2['paired_median_delta']:>+9.3f}")
        p("")
    g = res["grade_retest_this_roster"]
    p(f"  grade: this roster reproduces its own per-cell grade on {g['agreement']:.1%} of "
      f"{g['n_cells']} baseline cells (step {g['mean_abs_step']:.3f})")
    for v in VARIANTS:
        t = res["transforms"][v]["grade"]
        p(f"    {SHORT[v]}: {t['cells_moved_off_baseline']}/{t['n_cells']} cells move off baseline, "
          f"step {t['mean_abs_step']:.3f}, modal grade kept {t['modal_grade_kept']}/{t['n_papers']}")
    p("")
    q = res["queue"]
    if "mean_position_by_transform" in q:
        p(f"  queue: mean position {q['mean_position_by_transform']} against an expected "
          f"{q['expected_mean_position']}; rho(position, delta) = {q['rho_position_vs_delta']:+.3f}, "
          f"later-minus-earlier {q['later_minus_earlier_mean_delta']:+.4f} z")
    p("")
    for v in ("T1_endmatter", "T3_lengthen"):
        p(f"  {SHORT[v]}: same sign on both rosters = {res['verdict']['same_sign_both_rosters'][v]}, "
          f"above its own band = {res['verdict']['exceeds_own_rerun_band'][v]}")
    p(f"  => vendor diversity is a defence: {res['verdict']['vendor_diversity_is_a_defence']}")
    p(f"\n  written: {N2}/n2_analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

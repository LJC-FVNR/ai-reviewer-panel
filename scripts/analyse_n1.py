#!/usr/bin/env python3
"""N1 analysis: does a semantics-preserving presentation edit move a calibrated panel's score?

The pre-registered criterion, fixed before any of these numbers existed:

    PIA FAILS for transform t if a semantics-preserving transform moves the composite by more than
    re-running the same panel on the same text does.

So the comparison is against the panel's own test-retest band (|panel1 - panel2| on unchanged text),
not against zero. Zero is the wrong reference: no instrument returns the same number twice, and a
Delta smaller than the instrument's own scatter is not evidence of presentation sensitivity. Rank
displacement in the 16-paper reference field is reported as the headline because it is the unit a
venue acts on -- a 0.1 z shift matters only if it reorders papers.

THE INSTRUMENT IS FROZEN. Variants are z-scored with the mu/sd already in
calibration_params_portable.json. Refitting on the variants would let the treatment move the
yardstick measuring it, which would absorb the effect into the baseline and guarantee a null.

A DEFECT IN OUR OWN PRE-REGISTRATION, found by measurement on 2026-08-30 and reported rather than
reinterpreted. The criterion's second conjunct was ">=90% of papers keep their grade". Measured:

  - n=8 papers per arm, so the only achievable rates are 8/8 = 100% and 7/8 = 87.5%. The threshold is
    therefore satisfiable ONLY at 8/8: one paper flipping fails the arm.
  - The panel reproduces its own paper-level modal grade for just 75% of papers (12/16) on
    BYTE-IDENTICAL text, and its own per-cell grade for 81.2% of cells.

So the conjunct demanded that a manipulated arm be MORE self-consistent than the instrument is with
itself, and T2/T3 fail it at 7/8 -- a rate above the instrument's own 75%. The conjunct is reported as
mis-specified, and the grade axis is judged the way the composite axis already was: against a re-run of
the same panel, not against a fixed number. On that comparison every arm's grade movement is SMALLER
than a re-run's (mean |step| 0.150 vs 0.188; cell agreement 85% vs the 81.2% ceiling), and 67-83% of
the flips that do occur are at cells that also flip under a DIFFERENT transform. The grade is not
robust to presentation; it is too coarse to register presentation, which is the paper's thesis.

Usage: analyse_n1.py [--out n1_results.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import statistics as st

WS = "/path/to/workspace"
CAL = f"{WS}/paper_direction_98_calibration"
PARAMS = f"{CAL}/ICLR/calibration_params_portable.json"
BASE_REVIEWS = f"{CAL}/reviews"
VAR_REVIEWS = f"{WS}/ai_native_academia/n1_pia_5model/reviews"
GRADE_NUM = {"Reject": 1, "Reject and Resubmit": 2, "Major Revision": 3,
             "Minor Revision": 4, "Accept": 5}
SEED = 20260830


def composite(rev_dir, mu, sd, metrics):
    """Mean z over (slot, metric) channels within a panel, then over panels. Returns (comp, panels).

    Identical to the calibration's own definition -- averaging within a panel before averaging
    across panels, so a panel with a missing slot cannot outweigh a complete one.
    """
    per_panel = []
    for pdir in sorted(glob.glob(os.path.join(rev_dir, "panel*"))):
        zs = []
        for f in sorted(glob.glob(os.path.join(pdir, "R*.json"))):
            slot = os.path.basename(f)[:-5]
            try:
                rev = json.load(open(f))
            except Exception:
                continue
            for m in metrics:
                key = f"{slot}|{m}"
                md = rev.get("metrics", {}).get(m)
                if key in mu and md and isinstance(md.get("score"), (int, float)):
                    zs.append((md["score"] - mu[key]) / sd[key])
        if zs:
            per_panel.append(st.mean(zs))
    return (st.mean(per_panel) if per_panel else None), per_panel


def per_metric_z(rev_dir, mu, sd, metrics):
    """Mean z per metric, pooled over slots and panels. Returns {metric: z} for metrics present.

    This is the channel-level view the headline composite averages away, and it carries the argument.
    A reviewer marking DOWN a paper whose sentences were joined is behaving defensibly if the loss
    lands on clarity: the prose really did get harder to read. The same reviewer marking down its
    NOVELTY or STATISTICAL SOUNDNESS is not, because joining two sentences cannot alter what was
    proved or how it was tested. So the split between presentation channels and content channels is
    what separates "the panel judged the writing" from "presentation leaked into content".
    """
    acc: dict[str, list] = {}
    for f in sorted(glob.glob(os.path.join(rev_dir, "panel*", "R*.json"))):
        slot = os.path.basename(f)[:-5]
        try:
            rev = json.load(open(f))
        except Exception:
            continue
        for m in metrics:
            key = f"{slot}|{m}"
            md = rev.get("metrics", {}).get(m)
            if key in mu and md and isinstance(md.get("score"), (int, float)):
                acc.setdefault(m, []).append((md["score"] - mu[key]) / sd[key])
    return {m: st.mean(v) for m, v in acc.items()}


# Which channels a semantics-preserving edit is ALLOWED to move. Fixed here, from the definition of
# each metric, not chosen after seeing which ones moved.
PRESENTATION = {"clarity", "structure_compliance", "figure_quality", "calibration_honesty"}
CONTENT = {"significance", "novelty", "rigor", "statistical_soundness", "reproducibility",
           "related_work", "breadth_generality", "overall_recommendation"}

# Only T1 and T3 are presentation-invariance transforms. T2 rewrites claim strength (see the T2 block
# in pia_transforms.py: "significantly outperforms" -> "outperforms" withdraws a significance claim),
# so a score drop on T2 is not evidence of presentation sensitivity and the PIA verdict must not be
# read off it. Kept and reported as a claim-strength contrast.
PIA_VALID = {"T1_endmatter", "T3_lengthen"}
# Channels each transform may legitimately move, so a "leak" is only claimed where it cannot. Both
# presentation transforms are charged the same three, which is what lets one set of channel names serve
# both wings of F4.
#
# T3 is charged for figure_quality because audit_t3_captions.py measures it altering 63 of the 204 caption
# lines (31%) in 7 of the 8 papers, so caption readability really did change and figure_quality is not a
# clean leak. A hand diff gives 11 lines across 5 of 8 papers instead, off by roughly 5x, because its
# regex matches running-text references to figures and misses caption continuation lines. Run the audit
# rather than re-deriving it.
#
# T1 is charged for it on a different ground: the same audit gives it ZERO changed caption lines, but it
# moves every figure away from the sentence that refers to it, which is a real cost to how well the figure
# serves a reader. Charging it is the conservative reading -- it gives up a channel that could otherwise be
# counted as a leak -- and it is cheap, since T1's figure_quality median is the smallest of its three.
LEGITIMATE = {
    "T1_endmatter": {"structure_compliance", "clarity", "figure_quality"},
    "T3_lengthen": {"clarity", "structure_compliance", "figure_quality"},
    "T2_concede": {"clarity", "structure_compliance", "calibration_honesty",
                   "statistical_soundness", "breadth_generality", "significance", "rigor",
                   "novelty", "related_work", "overall_recommendation", "reproducibility"},
}


def grades(rev_dir):
    out = []
    for f in sorted(glob.glob(os.path.join(rev_dir, "panel*", "R*.json"))):
        try:
            g = json.load(open(f)).get("grade")
        except Exception:
            continue
        if g in GRADE_NUM:
            out.append(g)
    return out


def grade_cells(rev_dir):
    """{(panel, slot): grade}. Keyed so a variant cell can be paired with its own baseline cell.

    The composite is a z-average over 120 channels and is arithmetically damped; a grade is a single
    5-level draw and is the quantity a venue actually reads. So the grade axis has to be measured in
    the same PAIRED form, cell against cell, not as two histograms differenced.
    """
    out = {}
    for f in sorted(glob.glob(os.path.join(rev_dir, "panel*", "R*.json"))):
        try:
            g = json.load(open(f)).get("grade")
        except Exception:
            continue
        if g in GRADE_NUM:
            out[(os.path.basename(os.path.dirname(f)), os.path.basename(f)[:-5])] = g
    return out


def grade_retest(paper_ids, base_dir):
    """The panel's grade reproducibility on BYTE-IDENTICAL text: panel1 vs panel2, same slot.

    Without this the pre-registered ">=90% of papers keep their grade" conjunct cannot be read. It
    silently assumes the panel reproduces its own grade ~100% of the time; if it does not, the conjunct
    fails every arm including a perfectly null one, and the 90% is a property of the instrument rather
    than of the transform. Same error the composite criterion avoids by comparing to the test-retest
    band instead of to zero -- so the grade axis gets the same treatment.
    """
    same, absd = [], []
    for pid in paper_ids:
        cells = grade_cells(os.path.join(base_dir, pid))
        for s in sorted({slot for _, slot in cells}):
            g1, g2 = cells.get(("panel1", s)), cells.get(("panel2", s))
            if g1 and g2:
                same.append(g1 == g2)
                absd.append(abs(GRADE_NUM[g1] - GRADE_NUM[g2]))
    if not same:
        return None
    return {"n_pairs": len(same), "agreement": round(sum(same) / len(same), 4),
            "mean_abs_step": round(st.mean(absd), 4)}


def modal_grade(rev_dir):
    """The grade a venue would read off a panel: the modal grade over its reviews, ties -> lower.

    The pre-registered conjunct is worded "">=90% of PAPERS keep their grade"", so the paper is the unit
    and a per-cell rate answers a different question. Ties break DOWN (toward Reject) so the measure
    cannot flatter the panel by rounding a split decision upward.
    """
    gs = grades(rev_dir)
    if not gs:
        return None
    best = max(gs.count(g) for g in set(gs))
    return min((g for g in set(gs) if gs.count(g) == best), key=lambda g: GRADE_NUM[g])


def modal_grade_retest(paper_ids, base_dir):
    """Paper-level modal-grade reproducibility on identical text: panel1's mode vs panel2's mode."""
    same = []
    for pid in paper_ids:
        d = os.path.join(base_dir, pid)
        g1 = modal_grade_of_panel(d, "panel1")
        g2 = modal_grade_of_panel(d, "panel2")
        if g1 and g2:
            same.append(g1 == g2)
    if not same:
        return None
    return {"n_papers": len(same), "agreement": round(sum(same) / len(same), 4)}


def modal_grade_of_panel(rev_dir, panel):
    gs = [g for (p, _), g in grade_cells(rev_dir).items() if p == panel]
    if not gs:
        return None
    best = max(gs.count(g) for g in set(gs))
    return min((g for g in set(gs) if gs.count(g) == best), key=lambda g: GRADE_NUM[g])


def grade_flip_overlap(papers, tnames):
    """Do the SAME cells flip under transforms that have nothing in common?

    A cell that flips under all three manipulations is not reporting a transform effect. It is a cell
    sitting on a grade boundary, and it would flip on a re-run too -- which is measurable here, because
    the three transforms are mutually independent edits of the same eight papers. High overlap plus a
    per-transform agreement rate ABOVE the retest ceiling means the grade is not robust to
    presentation; it is too coarse to register anything, which is the same failure as 1 Accept in 480.
    """
    flips: dict[tuple, list] = {}
    for t in tnames:
        for p in papers:
            bc = grade_cells(os.path.join(BASE_REVIEWS, p))
            vc = grade_cells(os.path.join(VAR_REVIEWS, f"{p}__{t}"))
            for k in sorted(set(bc) & set(vc)):
                if bc[k] != vc[k]:
                    flips.setdefault((p,) + k, []).append(t)
    mult = {n: sum(1 for v in flips.values() if len(v) == n) for n in range(1, len(tnames) + 1)}
    shared = {t: (sum(1 for v in flips.values() if t in v and len(v) > 1),
                  sum(1 for v in flips.values() if t in v)) for t in tnames}
    return {"n_distinct_cells_that_ever_flip": len(flips),
            "cells_by_number_of_transforms": {str(k): v for k, v in mult.items()},
            "shared_fraction_per_transform": {
                t: round(s / n, 4) for t, (s, n) in shared.items() if n},
            "flipped_under_all": ["/".join(k) for k, v in sorted(flips.items())
                                  if len(v) == len(tnames)]}


def boot_median_ci(vals, n=5000, seed=SEED):
    if len(vals) < 3:
        return None, None
    rng = random.Random(seed)
    meds = sorted(st.median(rng.choices(vals, k=len(vals))) for _ in range(n))
    return meds[int(0.025 * n)], meds[int(0.975 * n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="n1_results.json")
    a = ap.parse_args()

    p = json.load(open(PARAMS))
    mu, sd, metrics = p["mu"], p["sd"], p["metrics"]
    recorded = p["per_paper_composite"]

    # ---- baselines, recomputed rather than trusted -------------------------------------------
    # The params file already lists per_paper_composite. Recomputing it from the stored reviews with
    # the same mu/sd is the check that this script's composite() matches the calibration's; if the
    # two disagree, every Delta below is measured with the wrong ruler and nothing else is worth
    # reading. Cheap check, total protection.
    base, base_panels = {}, {}
    for pid in recorded:
        c, pans = composite(os.path.join(BASE_REVIEWS, pid), mu, sd, metrics)
        if c is not None:
            base[pid], base_panels[pid] = c, pans
    drift = {k: round(base[k] - recorded[k], 4) for k in base if abs(base[k] - recorded[k]) > 0.002}
    print(f"baselines recomputed for {len(base)}/{len(recorded)} papers; "
          f"disagreements >0.002: {len(drift)}")
    if drift:
        print(f"  WARNING recompute mismatch (wrong ruler): {drift}")

    # test-retest band, measured here rather than borrowed
    gaps = [abs(v[0] - v[1]) for v in base_panels.values() if len(v) >= 2]
    band_median = st.median(gaps) if gaps else None
    band_mean = st.mean(gaps) if gaps else None

    field = sorted(base.values())
    adj_gaps = [field[i + 1] - field[i] for i in range(len(field) - 1)]
    adj_median = st.median(adj_gaps) if adj_gaps else None
    print(f"test-retest band: median {band_median:+.4f} / mean {band_mean:+.4f} "
          f"(n={len(gaps)}) | median adjacent-paper gap {adj_median:+.4f}")

    gr = grade_retest(list(base), BASE_REVIEWS)
    if gr:
        print(f"grade retest on identical text: {gr['agreement']:.1%} of {gr['n_pairs']} cells agree, "
              f"mean |step| {gr['mean_abs_step']:.3f} -> a transform cannot beat this ceiling")
    mgr = modal_grade_retest(list(base), BASE_REVIEWS)
    if mgr:
        print(f"modal-grade retest (paper level, identical text): {mgr['agreement']:.1%} of "
              f"{mgr['n_papers']} papers keep their modal grade across two panels")

    # ---- variants ------------------------------------------------------------------------------
    units = sorted(os.path.basename(d) for d in glob.glob(os.path.join(VAR_REVIEWS, "*"))
                   if os.path.isdir(d))
    by_t: dict[str, list] = {}
    for u in units:
        if "__" not in u:
            continue
        pid, tname = u.split("__", 1)
        if pid not in base:
            continue
        c, pans = composite(os.path.join(VAR_REVIEWS, u), mu, sd, metrics)
        if c is None:
            continue
        n_rev = len(glob.glob(os.path.join(VAR_REVIEWS, u, "panel*", "R*.json")))
        by_t.setdefault(tname, []).append(
            {"paper": pid, "baseline": round(base[pid], 4), "variant": round(c, 4),
             "delta": round(c - base[pid], 4), "n_reviews": n_rev,
             "panels": [round(x, 4) for x in pans]})

    results = {"instrument": "calibration_params_portable.json (frozen; not refit)",
               "test_retest_band_median": round(band_median, 4) if band_median else None,
               "test_retest_band_mean": round(band_mean, 4) if band_mean else None,
               "median_adjacent_paper_gap": round(adj_median, 4) if adj_median else None,
               "n_reference_field": len(base), "baseline_recompute_mismatches": drift,
               "grade_retest": gr, "modal_grade_retest": mgr, "transforms": {}}

    for tname in sorted(by_t):
        rows = by_t[tname]
        deltas = [r["delta"] for r in rows]
        absd = [abs(d) for d in deltas]
        lo, hi = boot_median_ci(deltas)
        # rank displacement: where the variant lands in the untouched 16-paper reference field
        disp = []
        for r in rows:
            others = sorted(v for k, v in base.items() if k != r["paper"])
            rb = sum(1 for v in others if v < r["baseline"])
            rv = sum(1 for v in others if v < r["variant"])
            r["rank_displacement"] = rv - rb
            disp.append(rv - rb)
        # Grade deltas are COUNTS, so they are only meaningful when both arms have the same number
        # of reviews. A variant arm still draining compares 5 variant grades against 10 baseline
        # ones and manufactures a spurious "-3 Minor Revision" out of nothing but incompleteness.
        gd, imbalanced = {}, []
        for r in rows:
            bg = grades(os.path.join(BASE_REVIEWS, r["paper"]))
            vg = grades(os.path.join(VAR_REVIEWS, f"{r['paper']}__{tname}"))
            if len(bg) != len(vg):
                imbalanced.append(f"{r['paper']}({len(bg)}b/{len(vg)}v)")
                continue
            for g in set(bg) | set(vg):
                gd[g] = gd.get(g, 0) + (vg.count(g) - bg.count(g))
        # Paired grade axis: same paper, same panel index, same slot, one variable changed. Reported
        # against grade_retest above rather than against 100% agreement.
        gsame, gstep, gsigned, msame = [], [], [], []
        for r in rows:
            bdir = os.path.join(BASE_REVIEWS, r["paper"])
            vdir = os.path.join(VAR_REVIEWS, f"{r['paper']}__{tname}")
            bc, vc = grade_cells(bdir), grade_cells(vdir)
            for k in sorted(set(bc) & set(vc)):
                gsame.append(bc[k] == vc[k])
                gstep.append(abs(GRADE_NUM[vc[k]] - GRADE_NUM[bc[k]]))
                gsigned.append(GRADE_NUM[vc[k]] - GRADE_NUM[bc[k]])
            mb, mv = modal_grade(bdir), modal_grade(vdir)
            r["modal_grade"] = [mb, mv]
            if mb and mv:
                msame.append(mb == mv)
        # Per-metric: paired per paper, so a paper's own baseline is its control on every channel.
        chan: dict[str, list] = {}
        for r in rows:
            bz = per_metric_z(os.path.join(BASE_REVIEWS, r["paper"]), mu, sd, metrics)
            vz = per_metric_z(os.path.join(VAR_REVIEWS, f"{r['paper']}__{tname}"), mu, sd, metrics)
            for m in set(bz) & set(vz):
                chan.setdefault(m, []).append(vz[m] - bz[m])
        chan_med = {m: round(st.median(v), 4) for m, v in sorted(chan.items())}
        pres = [chan_med[m] for m in PRESENTATION if m in chan_med]
        cont = [chan_med[m] for m in CONTENT if m in chan_med]

        if tname not in PIA_VALID:
            verdict = "NOT A PIA TRANSFORM (claim-strength contrast; see pia_transforms.py)"
        else:
            verdict = ("PASS (invariant: moves less than a re-run)"
                       if band_median is not None and st.median(absd) <= band_median
                       else "FAIL (presentation-sensitive)")
        # A leak is a channel the transform could not legitimately have moved.
        leaks = {m: v for m, v in chan_med.items()
                 if v < 0 and m not in LEGITIMATE.get(tname, set())}
        results["transforms"][tname] = {
            "n_papers": len(rows), "n_reviews": sum(r["n_reviews"] for r in rows),
            "median_delta": round(st.median(deltas), 4),
            "median_abs_delta": round(st.median(absd), 4),
            "delta_ci95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
            "n_negative": sum(1 for d in deltas if d < 0), "n_positive": sum(1 for d in deltas if d > 0),
            "median_rank_displacement": st.median(disp), "rank_displacements": disp,
            "grade_delta": {k: v for k, v in sorted(gd.items()) if v},
            "grade_delta_excluded_unequal_arms": imbalanced,
            "grade_paired": {
                "n_cells": len(gsame),
                "agreement": round(sum(gsame) / len(gsame), 4) if gsame else None,
                "mean_abs_step": round(st.mean(gstep), 4) if gstep else None,
                "mean_signed_step": round(st.mean(gsigned), 4) if gsigned else None,
                # A re-run's signed step is ~0 by symmetry (panel order is arbitrary), so a nonzero
                # signed step is the one grade quantity a re-run cannot manufacture: direction.
                "exceeds_retest_step": (bool(st.mean(gstep) > gr["mean_abs_step"])
                                        if gstep and gr else None),
                # The pre-registered unit. Reported alongside the cell rate rather than instead of it,
                # because the cell rate is what shows the flips are boundary noise (see overlap below).
                "n_papers": len(msame),
                "modal_grade_preserved": round(sum(msame) / len(msame), 4) if msame else None,
                "preserved_90pct_conjunct_papers": (bool(sum(msame) / len(msame) >= 0.90)
                                                    if msame else None),
                "cell_agreement_vs_retest_ceiling": (round(sum(gsame) / len(gsame) - gr["agreement"], 4)
                                                     if gsame and gr else None),
            } if gsame else None,
            "incomplete_units": [r["paper"] for r in rows if r["n_reviews"] < 10],
            "per_metric_median_delta": chan_med,
            "presentation_channel_median": round(st.median(pres), 4) if pres else None,
            "content_channel_median": round(st.median(cont), 4) if cont else None,
            "is_pia_transform": tname in PIA_VALID,
            "illegitimate_channel_deltas": dict(sorted(leaks.items(), key=lambda kv: kv[1])),
            "verdict": verdict, "per_paper": rows}
        print(f"\n{tname}: n={len(rows)} papers, {sum(r['n_reviews'] for r in rows)} reviews")
        print(f"  median delta {st.median(deltas):+.4f}  median |delta| {st.median(absd):+.4f}  "
              f"vs band {band_median:+.4f}  -> {verdict}")
        if lo is not None:
            print(f"  delta 95% CI [{lo:+.4f}, {hi:+.4f}]   sign split {sum(1 for d in deltas if d<0)}-/"
                  f"{sum(1 for d in deltas if d>0)}+")
        print(f"  median rank displacement {st.median(disp):+.1f} of {len(base)} "
              f"(displacements {disp})")
        print(f"  grade delta {results['transforms'][tname]['grade_delta']}"
              + (f"  [excluded, unequal arms: {', '.join(imbalanced)}]" if imbalanced else ""))
        gp = results["transforms"][tname]["grade_paired"]
        if gp:
            print(f"  grade paired: {gp['agreement']:.1%} of {gp['n_cells']} cells keep the grade "
                  f"(retest ceiling {gr['agreement']:.1%}) | mean |step| {gp['mean_abs_step']:.3f} "
                  f"vs retest {gr['mean_abs_step']:.3f} | signed {gp['mean_signed_step']:+.3f}")
            print(f"  grade at the PRE-REGISTERED unit: {gp['modal_grade_preserved']:.0%} of "
                  f"{gp['n_papers']} papers keep their modal grade "
                  f"-> >=90% conjunct {'PASS' if gp['preserved_90pct_conjunct_papers'] else 'FAIL'}")
        inc = results["transforms"][tname]["incomplete_units"]
        if inc:
            print(f"  INCOMPLETE (fewer than 10 reviews, delta is provisional): {', '.join(inc)}")
        pm = results["transforms"][tname]["presentation_channel_median"]
        cm = results["transforms"][tname]["content_channel_median"]
        print(f"  channels: presentation {pm:+.4f} vs content {cm:+.4f}")
        worst = sorted(chan_med.items(), key=lambda kv: kv[1])[:4]
        print("  most-moved: " + ", ".join(f"{m} {v:+.3f}" for m, v in worst))
        print("  LEAKS (channels this edit could not legitimately move): "
              + (", ".join(f"{m} {v:+.3f}" for m, v in list(leaks.items())[:4]) or "none"))

    # Cross-transform grade coincidence. Only meaningful once every transform is in, so it sits after
    # the loop rather than inside it.
    tnames = sorted(by_t)
    if len(tnames) > 1:
        papers = sorted({r["paper"] for rows in by_t.values() for r in rows})
        ov = grade_flip_overlap(papers, tnames)
        results["grade_flip_overlap"] = ov
        print(f"\ngrade flips across {len(tnames)} independent transforms of the same {len(papers)} "
              f"papers: {ov['n_distinct_cells_that_ever_flip']} distinct cells ever flip, "
              f"by transform count {ov['cells_by_number_of_transforms']}")
        print("  shared-with-another-transform fraction: "
              + ", ".join(f"{t} {v:.0%}" for t, v in ov["shared_fraction_per_transform"].items()))
        print(f"  flipped under ALL transforms: {', '.join(ov['flipped_under_all']) or 'none'}")

    json.dump(results, open(a.out, "w"), indent=1)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

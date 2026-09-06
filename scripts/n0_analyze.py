#!/usr/bin/env python3
"""What the 6-vendor panel says, computed so it can be compared with the 2-vendor panel and nothing else.

N0 re-points the cursor8 roster -- 8 slots over 6 vendors -- at the same 16 de-identified ICLR papers the
five-model panel read. Two runs, one corpus, one difference: who is reviewing. That makes three quantities
comparable and one not, and the not is the point of half this file.

  comparable   the grade distribution (256 reviews, a count, no interval worth arguing about)
  comparable   the variance split on the raw recommendation channel, IF the slot count is adjusted for
  comparable   inter-slot rank agreement on the same 16 papers
  not          any validity claim. The five-model rho against venue ratings on these 16 papers is +0.304
               with CI [-0.344, +0.771]; a cursor8 number lands inside that interval whatever it is.

Two things this computes that the five-model panel cannot express at all. First, the roster holds three
personas of one OpenAI model beside five other vendors, so reviewer disagreement splits into a between-vendor
part and a within-vendor part -- the paper's thesis says absolute grades are reviewer-specific, and this says
whether "reviewer" means "vendor". Second, an 8-slot sum of squares carries more degrees of freedom than a
5-slot one, so the raw share rises with the roster even under pure noise; the mean-square components below are
what a 5-vs-8 comparison is allowed to use.

  python3 n0_analyze.py [--allow-partial]      # -> n0_cursor8_iclr/n0_analysis.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import itertools
import json
import os
import random
import statistics as st

AN = os.path.dirname(os.path.abspath(__file__))
CAL5 = os.path.join(os.path.dirname(AN), "paper_direction_98_calibration")
OUT = f"{AN}/n0_cursor8_iclr"
REV = f"{OUT}/reviews"
MODELS = "/path/to/workspace/paper_direction_72/cursor_panel/panel_models.json"
PARAMS = f"{OUT}/calibration_params_cursor8_iclr.json"
GRADES = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]
ORDER = {g: i for i, g in enumerate(GRADES)}
PANELS = 2

# The five-model numbers this run is measured against, all on these same 16 published papers, all printed in
# the paper. Transcribed here so the comparison is visible in the output rather than done in the reader's head.
FIVE = dict(n_reviews=160, accept_count=1, modal_pct=68.8, paper_pct=39.1, slot_pct=18.8, ratio=0.48,
            spread=0.97, interslot_median=0.710, rerun_median=0.160, rerun_p90=0.333, adjacent=0.115)


def reviews():
    """-> {(paper, panel, slot): review}, skipping the empty files a resumable run leaves behind."""
    out = {}
    for f in sorted(glob.glob(f"{REV}/*/panel*/C?.json")):
        if os.path.getsize(f) > 2:
            p = f.split("/")
            out[(p[-3], p[-2], os.path.basename(f)[:2])] = json.load(open(f))
    return out


def score(r, metric):
    """cursor8 writes scores as strings, the five-model runner writes ints; both mean the same integer."""
    v = r.get("metrics", {}).get(metric, {}).get("score")
    return None if v in (None, "") else float(v)


def zmean(r, slot, mu, sd, metrics):
    z = [(score(r, m) - mu[f"{slot}|{m}"]) / sd[f"{slot}|{m}"]
         for m in metrics if score(r, m) is not None and sd.get(f"{slot}|{m}")]
    return st.mean(z) if z else None


def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            for k in range(i, j + 1):
                r[s[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def twoway(obs):
    """Paper x slot on the raw recommendation channel, reported two ways because only one of them travels.

    obs is (paper, slot, score) and the design is balanced, so the effects are orthogonal and the sums of
    squares subtract cleanly. The percentages are the same definition the paper prints for the five-model
    panel -- and they are not comparable across rosters, because SS_slot has (k-1) degrees of freedom and so
    grows with k even when every slot is exchangeable. The variance *components* (Searle's estimators for a
    balanced two-way random model) divide each SS by its df and subtract the residual, which removes that
    dependence: var_slot is an estimate of the same population quantity whether k is 5 or 8.
    """
    papers = sorted({o[0] for o in obs})
    slots = sorted({o[1] for o in obs})
    a, b = len(papers), len(slots)
    n = len(obs) / (a * b)                                   # replicates per cell = panels
    gm = st.mean(o[2] for o in obs)
    ss_tot = sum((o[2] - gm) ** 2 for o in obs)
    ss, means = {}, {}
    for i, name in ((0, "paper"), (1, "slot")):
        g: dict[str, list] = {}
        for o in obs:
            g.setdefault(o[i], []).append(o[2])
        ss[name] = sum(len(v) * (st.mean(v) - gm) ** 2 for v in g.values())
        means[name] = {k: st.mean(v) for k, v in g.items()}
    cell: dict[tuple, list] = {}
    for o in obs:
        cell.setdefault((o[0], o[1]), []).append(o[2])
    ss_cells = sum(len(v) * (st.mean(v) - gm) ** 2 for v in cell.values())
    ss_err = ss_tot - ss_cells
    ss_int = ss_cells - ss["paper"] - ss["slot"]
    ms_err = ss_err / (a * b * (n - 1)) if n > 1 else float("nan")
    ms_int = ss_int / ((a - 1) * (b - 1))
    v_int = max(0.0, (ms_int - ms_err) / n)
    v_paper = max(0.0, (ss["paper"] / (a - 1) - ms_int) / (b * n))
    v_slot = max(0.0, (ss["slot"] / (b - 1) - ms_int) / (a * n))
    tot = v_paper + v_slot + v_int + ms_err
    sm = list(means["slot"].values())
    # Range over 8 slots is wider than over 5 for the same population, so the range is reported (it is what
    # the paper prints) and the standard deviation beside it (it is what may be compared across rosters).
    return dict(n_obs=len(obs), n_papers=a, n_slots=b,
                paper_pct=100 * ss["paper"] / ss_tot, slot_pct=100 * ss["slot"] / ss_tot,
                ratio=ss["slot"] / ss["paper"], spread=max(sm) - min(sm), slot_sd=st.stdev(sm),
                var_paper=v_paper, var_slot=v_slot, var_interaction=v_int, var_resid=ms_err,
                var_paper_pct=100 * v_paper / tot, var_slot_pct=100 * v_slot / tot,
                slot_means={k: round(v, 3) for k, v in sorted(means["slot"].items())})


def nested(obs, vendor_of):
    """Split reviewer disagreement into vendor and slot-within-vendor.

    Three of the eight slots are personas of one OpenAI model, so the two levels are separately estimable:
    if reviewer identity is really vendor identity, the vendor line takes most of it and the persona line
    almost none. Unbalanced across vendors (3, 1, 1, 1, 1, 1), so the vendor sum of squares is computed from
    slot means weighted by slot count -- a Type-I decomposition, vendor entered first.
    """
    slots: dict[str, list] = {}
    for o in obs:
        slots.setdefault(o[1], []).append(o[2])
    sm = {s: st.mean(v) for s, v in slots.items()}
    gm = st.mean(o[2] for o in obs)
    ven: dict[str, list] = {}
    for s, m in sm.items():
        ven.setdefault(vendor_of[s], []).append((s, m, len(slots[s])))
    ss_slot = sum(len(v) * (sm[s] - gm) ** 2 for s, v in slots.items())
    ss_ven = 0.0
    for v, members in ven.items():
        w = sum(n for _, _, n in members)
        vmean = sum(m * n for _, m, n in members) / w
        ss_ven += w * (vmean - gm) ** 2
    multi = {v: m for v, m in ven.items() if len(m) > 1}
    return dict(n_vendors=len(ven), ss_slot=ss_slot, ss_vendor=ss_ven,
                vendor_share_of_slot=100 * ss_ven / ss_slot if ss_slot else float("nan"),
                vendor_means={v: round(sum(m * n for _, m, n in mem) / sum(n for _, _, n in mem), 3)
                              for v, mem in sorted(ven.items())},
                within_vendor_spread={v: round(max(m for _, m, _ in mem) - min(m for _, m, _ in mem), 3)
                                      for v, mem in sorted(multi.items())})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-partial", action="store_true",
                    help="print anyway. A hole biases every mu and sd it touches; only for watching a run.")
    a = ap.parse_args()

    panel = json.load(open(MODELS))["panel"]
    slots = [s["slot"] for s in panel]
    vendor_of = {s["slot"]: s["vendor"] for s in panel}
    disp = {s["slot"]: s["display"] for s in panel}
    R = reviews()
    papers = sorted({k[0] for k in R})
    want = len(papers) * PANELS * len(slots)

    # The only difference between this run and the five-model run must be who is reviewing. Two runners
    # assemble the prompt independently -- one substitutes the manuscript into the template in Python, the
    # other in shell -- so "same prompt" is a claim about two code paths and is checked, not assumed. A
    # mismatch here would make every cross-panel comparison below a comparison of prompts.
    p_same, p_differ = [], []
    for p in papers:
        a1 = f"{REV}/{p}/prompt.md"
        # Any slot's copy will do: the five-model runner substitutes the manuscript into the template once
        # per paper, so the prompt does not vary by slot. Globbing rather than naming panel1/R1 because a
        # run that was resumed has not necessarily kept that particular file.
        b = sorted(glob.glob(f"{CAL5}/reviews/{p}/panel*/R?.prompt.txt"))
        if os.path.exists(a1) and b:
            h = [hashlib.sha256(open(x, "rb").read()).hexdigest() for x in (a1, b[0])]
            (p_same if h[0] == h[1] else p_differ).append(p)
    print(f"prompt identity: {len(p_same)} of {len(p_same) + len(p_differ)} papers have a byte-identical "
          f"assembled prompt across the two panels"
          + (f"  -- MISMATCH on {p_differ}" if p_differ else " (sha256)"))

    holes = [(p, f"panel{i}", s) for p in papers for i in range(1, PANELS + 1) for s in slots
             if (p, f"panel{i}", s) not in R]
    print(f"{len(R)} reviews over {len(papers)} papers x {PANELS} panels x {len(slots)} slots "
          f"({len(R)}/{want} of this tree, 256 when all 16 papers are in)")
    if holes:
        by_slot: dict[str, int] = {}
        for _, _, s in holes:
            by_slot[s] = by_slot.get(s, 0) + 1
        print(f"  {len(holes)} missing: " + ", ".join(f"{s} {n}" for s, n in sorted(by_slot.items())))
        if not a.allow_partial:
            print("\nrefusing to report on a tree with holes -- a slot that is missing papers has a mu and sd\n"
                  "fitted on a different set than its neighbours, which shifts every z it produces.\n"
                  "Re-run run_n0.sh (it resumes), or pass --allow-partial to watch progress.")
            return 2

    # --- section 3: does the grade compression survive six vendors? ---------------------------------------
    g = [r.get("grade") or r.get("overall_grade") for r in R.values()]
    counts = {x: g.count(x) for x in GRADES}
    unknown = [x for x in g if x not in ORDER]
    print(f"\ngrades over {len(g)} reviews of papers a top venue published")
    for x in GRADES:
        print(f"  {x:<22} {counts[x]:>4}  {100 * counts[x] / len(g):>5.1f}%"
              + ("   <- five-model panel: 1 in 160" if x == "Accept" else ""))
    if unknown:
        print(f"  unparsed grade on {len(unknown)} reviews: {sorted(set(unknown))}")
    modal = max(GRADES, key=lambda x: counts[x])
    print(f"  modal {modal} at {100 * counts[modal] / len(g):.1f}%   "
          f"(five-model: Major Revision at {FIVE['modal_pct']}%)")

    # The distribution above is a mixture, and which reviewer a grade came from is the whole question. A row
    # of counts per slot is therefore not a diagnostic for this table -- it IS the table. If the grades were a
    # property of the manuscripts, these eight rows would look alike.
    per_slot_g = {s: {x: 0 for x in GRADES} for s in slots}
    for (p, pan, s), r in R.items():
        gr = r.get("grade")
        if gr in per_slot_g[s]:
            per_slot_g[s][gr] += 1
    # The same count for the roster this one replaces, on the same sixteen papers and the same 32 reviews per
    # slot, so that the two rosters' rows can be read against each other rather than against two aggregates.
    # It is measured here and not in grade_table.py because that script counts populations, not slots.
    five_slot_g: dict[str, dict[str, int]] = {}
    for f in sorted(glob.glob(f"{CAL5}/reviews/*/panel*/R?.json")):
        if os.path.getsize(f) < 2:
            continue
        gr = json.load(open(f)).get("grade")
        row = five_slot_g.setdefault(os.path.basename(f)[:2], {x: 0 for x in GRADES})
        if gr in row:
            row[gr] += 1

    print(f"\nthe same {len(papers)} papers, graded by each slot in turn")
    print(f"  {'':<4}{'model':<22}{'vendor':<10}" + "".join(f"{x.split()[0][:5]:>7}" for x in GRADES) + "     n")
    for s in slots:
        c = per_slot_g[s]
        n = sum(c.values())
        if n:
            print(f"  {s:<4}{disp[s]:<22}{vendor_of[s]:<10}" + "".join(f"{c[x]:>7}" for x in GRADES) + f"  {n:>4}")
    acc_slots = {s: c["Accept"] for s, c in per_slot_g.items() if c["Accept"]}
    print(f"  every Accept in this run came from {len(acc_slots)} of {len(slots)} slots: "
          + ", ".join(f"{s} {n}" for s, n in acc_slots.items()) if acc_slots else "  no Accept from any slot")

    bypanel: dict[tuple, list] = {}
    for (p, pan, s), r in R.items():
        bypanel.setdefault((p, pan), []).append(r.get("grade"))
    bypanel = {k: v for k, v in bypanel.items() if all(x in ORDER for x in v)}
    ladder = {
        "every reviewer Minor+": lambda gs: all(ORDER[x] >= ORDER["Minor Revision"] for x in gs),
        "at least one Accept": lambda gs: any(x == "Accept" for x in gs),
        "modal grade Minor+": lambda gs: ORDER[st.mode(gs)] >= ORDER["Minor Revision"],
        "every reviewer Major+": lambda gs: all(ORDER[x] >= ORDER["Major Revision"] for x in gs),
    }
    print(f"\nthe acceptance ladder, over {len(bypanel)} panels of 8")
    lad = {}
    for label, pred in ladder.items():
        hit = {k: pred(v) for k, v in bypanel.items()}
        ps = {p for p, _ in hit}
        lad[label] = dict(panels=sum(hit.values()),
                          papers_any=sum(any(hit[(p, k)] for q, k in hit if q == p) for p in ps),
                          papers_both=sum(all(hit[(p, k)] for q, k in hit if q == p) for p in ps))
        print(f"  {label:<22} {lad[label]['panels']:>3} panels   "
              f"{lad[label]['papers_both']} of {len(ps)} papers in both panels")

    # --- is severity a function of how long the reviewer thought? ----------------------------------------
    # Eight points, so this is an observation and not a finding, and it is reported as one. It is worth the
    # four lines because it names a mechanism a venue can act on: if the harsh slots are the ones that spend
    # the most tokens, then "grade" is partly a budget setting, which is not a property of the manuscript.
    sev, spend = {}, {}
    for s in slots:
        recs = [score(r, "overall_recommendation") for (p, pan, q), r in R.items()
                if q == s and score(r, "overall_recommendation") is not None]
        outs = [json.load(open(f)).get("usage", {}).get("outputTokens") or 0
                for f in glob.glob(f"{REV}/*/panel*/{s}.out.meta.json")]
        outs = [o for o in outs if o]
        if recs and outs:
            sev[s], spend[s] = st.mean(recs), st.median(outs)
    if len(sev) >= 5:
        ks = sorted(sev)
        rho_spend = spearman([spend[s] for s in ks], [sev[s] for s in ks])
        print(f"\nseverity against output tokens, {len(ks)} slots: rho {rho_spend:+.3f}"
              "   (8 points -- an observation, not a result)")
        print("  " + "  ".join(f"{s} {sev[s]:.1f}@{spend[s] / 1000:.1f}k" for s in
                               sorted(ks, key=lambda x: sev[x])))

    # --- the composite, on cursor8's own parameters ------------------------------------------------------
    fitted = os.path.exists(PARAMS)
    res = dict(n_reviews=len(R), n_papers=len(papers), n_slots=len(slots), holes=len(holes),
               grade_counts=counts, modal_grade=modal, ladder=lad, five_model=FIVE,
               per_slot_grades=per_slot_g, five_model_per_slot_grades=five_slot_g,
               vendor_of_slot=vendor_of,
               mean_recommendation_by_slot={k: round(v, 3) for k, v in sev.items()},
               median_output_tokens_by_slot=spend,
               rho_severity_vs_output_tokens=round(rho_spend, 4) if len(sev) >= 5 else None,
               vendors=sorted(set(vendor_of.values())), slot_display=disp)

    if not fitted:
        print(f"\nno {os.path.basename(PARAMS)} yet -- run_n0.sh fits it after the last review lands.\n"
              "Everything above is calibration-free; the yardsticks below are not.")
    else:
        cal = json.load(open(PARAMS))
        mu, sd, metrics = cal["mu"], cal["sd"], cal["metrics"]
        comp: dict[str, dict[str, float]] = {}
        for (p, pan, s), r in R.items():
            v = zmean(r, s, mu, sd, metrics)
            if v is not None:
                comp.setdefault(p, {}).setdefault(pan, []).append(v)
        pan_comp = {p: {k: st.mean(v) for k, v in d.items()} for p, d in comp.items()}
        paper_comp = {p: st.mean(d.values()) for p, d in pan_comp.items()}

        steps = sorted(abs(d["panel1"] - d["panel2"]) for d in pan_comp.values() if len(d) == 2)
        rerun_med, rerun_p90 = st.median(steps), steps[int(0.9 * (len(steps) - 1))]
        order = sorted(paper_comp.values())
        adjacent = st.median([b - a for a, b in zip(order, order[1:])])
        print("\nyardsticks on this panel -- measured, not inherited from the five-model panel")
        print(f"  re-run band, median |dz| over {len(steps)} papers   {rerun_med:.3f}"
              f"   (five-model {FIVE['rerun_median']:.3f})")
        print(f"  re-run band, p90 (14th of 16 ordered)              {rerun_p90:.3f}"
              f"   (five-model {FIVE['rerun_p90']:.3f})")
        print(f"  adjacent-paper gap, median                        {adjacent:.3f}"
              f"   (five-model {FIVE['adjacent']:.3f})")
        print(f"  -> a step between neighbours is {'smaller' if adjacent < rerun_med else 'LARGER'} than the "
              f"panel's own movement, so the field {'cannot' if adjacent < rerun_med else 'can'} be ordered "
              f"finely on 6 vendors either" if adjacent < rerun_med else "")
        res.update(rerun_median=round(rerun_med, 4), rerun_p90=round(rerun_p90, 4),
                   adjacent_gap=round(adjacent, 4),
                   composite_span=[round(order[0], 4), round(order[-1], 4)],
                   retest_rho=round(spearman(*([[pan_comp[p][f"panel{i}"] for p in sorted(pan_comp)
                                                if len(pan_comp[p]) == 2] for i in (1, 2)])), 4))

        # per-slot orderings: agreement between vendors, and between personas of one vendor
        ps: dict[str, dict[str, list]] = {}
        for (p, pan, s), r in R.items():
            v = zmean(r, s, mu, sd, metrics)
            if v is not None:
                ps.setdefault(s, {}).setdefault(p, []).append(v)
        ps = {s: {p: st.mean(v) for p, v in d.items()} for s, d in ps.items()}
        keys = sorted(paper_comp)
        pairs = {(x, y): spearman([ps[x][k] for k in keys], [ps[y][k] for k in keys])
                 for x, y in itertools.combinations(sorted(ps), 2) if all(k in ps[x] and k in ps[y] for k in keys)}
        allp = sorted(pairs.values())
        cross = sorted(v for (x, y), v in pairs.items() if vendor_of[x] != vendor_of[y])
        same = sorted(v for (x, y), v in pairs.items() if vendor_of[x] == vendor_of[y])
        print(f"\ninter-slot rank agreement on the same {len(keys)} papers, {len(pairs)} pairs")
        print(f"  median {st.median(allp):.3f}, min {allp[0]:.3f}, max {allp[-1]:.3f}"
              f"   (five-model, 10 pairs: median {FIVE['interslot_median']:.3f})")
        if same:
            print(f"  {len(same)} same-vendor pairs   median {st.median(same):.3f}")
            print(f"  {len(cross)} cross-vendor pairs  median {st.median(cross):.3f}")
            print("  -> personas of one model agree "
                  f"{'more' if st.median(same) > st.median(cross) else 'no more'} with each other than "
                  "vendors do with each other")
        res.update(prompt_identical=len(p_same), prompt_mismatch=p_differ, interslot_median=round(st.median(allp), 4), interslot_min=round(allp[0], 4),
                   interslot_same_vendor=round(st.median(same), 4) if same else None,
                   interslot_cross_vendor=round(st.median(cross), 4) if cross else None,
                   n_pairs=len(pairs))

        # --- the roster swap: what changes when every model in the panel is replaced -------------------
        # Each roster is z-scored against its own mu and sd, so this compares two orderings, not two
        # scales -- which is the only comparison a paper claiming "rank, not grade" is entitled to make.
        # The per-paper differences are taken at PANEL resolution, five reviews against eight, because the
        # quantity they have to be measured against is a single panel's re-run of itself. Averaging both
        # rosters over their two panels first would make the swap look smaller than the re-run for the
        # arithmetic reason that it averages more reviews, which would prove nothing.
        f5p = f"{CAL5}/ICLR/calibration_params_portable.json"
        if os.path.exists(f5p):
            f5c = json.load(open(f5p))
            f5: dict[str, dict[str, list]] = {}
            for f in sorted(glob.glob(f"{CAL5}/reviews/*/panel*/R?.json")):
                if os.path.getsize(f) > 2:
                    v = zmean(json.load(open(f)), os.path.basename(f)[:2],
                              f5c["mu"], f5c["sd"], f5c["metrics"])
                    if v is not None:
                        f5.setdefault(f.split("/")[-3], {}).setdefault(f.split("/")[-2], []).append(v)
            f5 = {p: {k: st.mean(v) for k, v in d.items()} for p, d in f5.items()}
            ks = sorted(set(f5) & set(pan_comp))
            w5 = sorted(abs(f5[p]["panel1"] - f5[p]["panel2"]) for p in ks)
            w8 = sorted(abs(pan_comp[p]["panel1"] - pan_comp[p]["panel2"]) for p in ks)
            sw = sorted(abs(f5[p][x] - pan_comp[p][y]) for p in ks
                        for x in ("panel1", "panel2") for y in ("panel1", "panel2"))
            print(f"\n|movement in composite z| at panel resolution, over {len(ks)} papers")
            for lbl, v in (("re-run, five-model panel against itself", w5),
                           ("re-run, this panel against itself", w8),
                           ("roster swap, five-model against this panel", sw)):
                print(f"  {lbl:<44} n={len(v):>3}  median {st.median(v):.3f}  "
                      f"p90 {v[int(0.9 * (len(v) - 1))]:.3f}  max {max(v):.3f}")
            print(f"  -> replacing every model in the panel moves a paper "
                  f"{'LESS' if st.median(sw) < st.median(w5) else 'more'} than re-running the same panel on "
                  f"byte-identical text ({st.median(sw):.3f} against {st.median(w5):.3f})")
            f5_paper = {p: st.mean(f5[p].values()) for p in ks}
            rho_sw = spearman([paper_comp[p] for p in ks], [f5_paper[p] for p in ks])
            bs = sorted(spearman([paper_comp[ks[i]] for i in idx], [f5_paper[ks[i]] for i in idx])
                        for idx in [random.Random(11 + b).choices(range(len(ks)), k=len(ks))
                                    for b in range(4000)])
            d1 = sorted(spearman([paper_comp[ks[j]] for j in range(len(ks)) if j != i],
                                 [f5_paper[ks[j]] for j in range(len(ks)) if j != i]) for i in range(len(ks)))
            print(f"  the two rosters' orderings of these {len(ks)} papers: rho {rho_sw:+.3f}  "
                  f"CI [{bs[100]:+.3f}, {bs[-101]:+.3f}]  drop-one {d1[0]:+.3f} .. {d1[-1]:+.3f}")
            res["roster_swap"] = dict(
                n_papers=len(ks), rho=round(rho_sw, 4), ci=[round(bs[100], 4), round(bs[-101], 4)],
                drop_one=[round(d1[0], 4), round(d1[-1], 4)],
                median_rerun_five=round(st.median(w5), 4), median_rerun_this=round(st.median(w8), 4),
                median_swap=round(st.median(sw), 4), p90_swap=round(sw[int(0.9 * (len(sw) - 1))], 4),
                max_swap=round(max(sw), 4),
                # The pairs the rho is computed over. A figure of this comparison has to draw the same sixteen
                # points the correlation is taken on, and recomputing them in a figure script would be a second
                # implementation of the calibration -- which is how a figure comes to quote an already-rounded
                # value, the defect unchecked.py exists for. Paper resolution, as the rho is.
                pairs={p: [round(f5_paper[p], 4), round(paper_comp[p], 4)] for p in ks})

            # The validity comparison pre-registration says not to lean on, computed so that a reader who
            # asks for it finds it with its interval attached rather than absent.
            hrp = f"{AN}/reject_arm/accepted_arm_human_ratings.json"
            if os.path.exists(hrp):
                hr = json.load(open(hrp))
                hk = [p for p in ks if p in hr]
                h = [hr[p]["human"] for p in hk]
                print(f"\nagainst the venue's own ratings on the {len(hk)} published papers that carry them"
                      "  (pre-registered as underpowered)")
                res["validity_published"] = {}
                for lbl, comp_of in (("this panel, 6 vendors", paper_comp), ("five-model panel", f5_paper)):
                    x = [comp_of[p] for p in hk]
                    b2 = sorted(v for v in (spearman([x[i] for i in idx], [h[i] for i in idx])
                                            for idx in [random.Random(23 + b).choices(range(len(hk)), k=len(hk))
                                                        for b in range(4000)]) if v == v)
                    print(f"  {lbl:<24} rho {spearman(x, h):+.3f}   "
                          f"CI [{b2[int(.025 * len(b2))]:+.3f}, {b2[int(.975 * len(b2))]:+.3f}]")
                    res["validity_published"][lbl] = dict(
                        n=len(hk), rho=round(spearman(x, h), 4),
                        ci=[round(b2[int(.025 * len(b2))], 4), round(b2[int(.975 * len(b2))], 4)])

    # --- section 4: the vendor-width variance row --------------------------------------------------------
    obs = [(p, s, score(r, "overall_recommendation")) for (p, _, s), r in R.items()
           if score(r, "overall_recommendation") is not None]
    if len({o[0] for o in obs}) > 1 and len(obs) == want:
        d = twoway(obs)
        # The five-model side, recomputed here on the same 16 papers through the same function rather than
        # transcribed, so that "the rosters differ and nothing else does" is a property of the code.
        five_obs = [(f.split("/")[-3], os.path.basename(f)[:2],
                     float(json.load(open(f))["metrics"]["overall_recommendation"]["score"]))
                    for p in papers for f in sorted(glob.glob(f"{CAL5}/reviews/{p}/panel*/R?.json"))
                    if os.path.getsize(f) > 2]
        d5 = twoway(five_obs) if len({o[1] for o in five_obs}) == 5 else None
        print(f"\nwhere the variance sits, raw recommendation channel, {d['n_obs']} observations")
        print(f"  paper      {d['paper_pct']:>5.1f}%   (five-model, 5 slots: {FIVE['paper_pct']}%)")
        print(f"  reviewer   {d['slot_pct']:>5.1f}%   (five-model, 5 slots: {FIVE['slot_pct']}%)"
              "   <- shares are not comparable across roster sizes")
        print(f"  reviewer/paper {d['ratio']:.2f}      (five-model {FIVE['ratio']})")
        print(f"  slot baseline spread {d['spread']:.2f} pts   (five-model {FIVE['spread']})")
        print("\n  df-adjusted variance components, which are what a 5-vs-8 comparison may use")
        hdr = f"    {'':<26}{'6 vendors, 8 slots':>20}"
        print(hdr + (f"{'2 vendors, 5 slots':>20}" if d5 else "   (five-model recompute unavailable)"))
        for label, key, fmt in (("paper variance", "var_paper", "{:.4f}"), ("reviewer variance", "var_slot", "{:.4f}"),
                                ("interaction", "var_interaction", "{:.4f}"), ("residual", "var_resid", "{:.4f}"),
                                ("reviewer % of total", "var_slot_pct", "{:.1f}%"),
                                ("sd of slot baselines, pts", "slot_sd", "{:.3f}")):
            print(f"    {label:<26}" + f"{fmt.format(d[key]):>20}"
                  + (f"{fmt.format(d5[key]):>20}" if d5 else ""))
        if d5:
            print(f"    -> widening the roster from 2 vendors to 6 {'lowers' if d['var_slot'] < d5['var_slot'] else 'RAISES'}"
                  f" the reviewer variance component, {d5['var_slot']:.3f} -> {d['var_slot']:.3f}."
                  "\n       The pre-registered mechanism test predicted a fall if 5 slots were"
                  "\n       merely too few; it is answered by the sign of this line, not by its size.")
            res["five_model_recomputed"] = d5
        nd = nested(obs, vendor_of)
        print(f"\n  reviewer disagreement split over {nd['n_vendors']} vendors")
        print(f"    vendor takes {nd['vendor_share_of_slot']:.1f}% of the between-slot sum of squares")
        print("    vendor means: " + ", ".join(f"{v} {m:+.2f}" for v, m in nd["vendor_means"].items()))
        for v, s in nd["within_vendor_spread"].items():
            print(f"    within {v}, {s:.2f} pts between personas of one model")
        res["variance"] = d
        res["vendor_nested"] = nd
    else:
        print("\nvariance split needs the complete balanced tree; skipping.")

    json.dump(res, open(f"{OUT}/n0_analysis.json", "w"), indent=1, default=str)
    print(f"\nwrote n0_cursor8_iclr/n0_analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""F1, the icon: one panel per claim -- the grade does not separate, the ranking orders but coarsely.

Named by the claims and not by the title, which is what this line used to do. The panels never changed;
the title changed twice underneath them, and a docstring quoting it went stale silently both times.

(a) the grade axis collapses, in two views of the same axis. Above, four ICLR 2026 populations: Major
    Revision is the mode for every one of them, and accepted papers are near-twins of the high-rated
    REJECTED ones, across a boundary the venue treated as decisive. Below, the second roster's eight
    slots over six vendors reading the sixteen accepted papers, 32 reviews each: read down, a grade
    looks like a property of the paper; read across, it is a property of the slot -- one slot supplies
    every Accept the roster awards and another answers published work with Reject-and-Resubmit 29
    times in 32. The roster was run as the replication three sections lean on and reached the reader
    as a table row, which for a claim of that size is the same as not having been run.

    The two groups share the axis because they are the same measurement, and the axis is a share
    rather than a count because the rows have different denominators: 160 reviews for a population,
    32 for a slot. Every segment prints its own count, so the denominator is never the thing a reader
    has to remember.
(b) the composite axis orders, and the panel qualifies it arm by arm. Pooled rho=+0.595, but the two
    arms were sampled at the rating scale's extremes, so each cluster prints its own coefficient:
    the lower arm rho=-0.05 (p=.85), the higher arm rho=+0.56 (p=.02). One arm orders its own papers
    and the other does not, which is a mixed result and is drawn as one.

    Those two coefficients are recomputed from the plotted points. The panel used to annotate itself
    from d["q0"]["within"], which is the composite against the hour each paper was scored -- a
    different variable, the same shape of number, and no way to tell from the page. That is also why
    the claim above changed: read against the clock the higher arm looked like nothing, and the
    caption concluded the instrument cannot order papers of similar quality. Read against the rating
    it can, in one of the two arms.

Both panels are third-party ICLR 2026 data. Panel (b) deliberately stays INSIDE the reject pile: a
scatter mixing accepted and rejected papers would confound the correlation with the accept/reject
stage, and the within-pile version is the one that carries the claim.

Drawn at final placed size (5.5in = NeurIPS text width), so nothing is rescaled after the fact and
the type sizes here are the type sizes on the page.
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import rng, sgn  # noqa: E402
# One definition of a rank correlation for the whole repository. reproduce.py owns it, is standard-library
# only, and is the file that checks this figure's numbers against the page, so importing from it means the
# figure and its expectation row cannot disagree about what was computed.
from reproduce import spearman_p  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

WS = "/path/to/workspace"
REJ = f"{WS}/ai_native_academia/reject_arm/analysis_results.json"
# The second roster's own analysis file, read rather than recomputed: a figure that re-derived a slot's
# grade distribution from the reviews would be a second implementation of the count the appendix table
# prints, and the two could then disagree on the page with nothing to catch it.
C8 = f"{WS}/ai_native_academia/n0_cursor8_iclr/n0_analysis.json"
CAL = f"{WS}/paper_direction_98_calibration/ICLR/calibration_params_portable.json"
OUT = f"{WS}/ai_native_academia/figs"

GRADES = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]
# Ordinal scale -> sequential ramp, colourblind-safe, dark at the reject end.
GCOL = ["#7f2704", "#d94801", "#fdae6b", "#9ecae1", "#08519c"]
# One line per label now, not two: eleven rows share the panel, so the row pitch is set by the type and a
# two-line label would collide with the bar above it.
ROWS = [("accepted_ref", "ICLR accepted (16)"),
        ("rejected_high", "ICLR rejected, higher-rated (16)"),
        ("rejected_low", "ICLR rejected, lower-rated (16)")]
# Row positions in panel (a). The populations sit at 0-2 and the eight slots below a blank row that
# carries the group's own header, so the two groups read as two groups without a second axis.
Y_POP = [0.0, 1.0, 2.0]
Y_HEAD = 3.15
Y_SLOT0 = 4.15
Y_NOTE = -1.05

# Type hierarchy: distinct tiers matter more than any single floor.
PT_TITLE, PT_LAB, PT_TICK, PT_ANN = 8.0, 7.5, 7.0, 6.4
# The grotesque the figure guidelines of this literature ask for, in the one flavour of it that embeds
# correctly. Its advance widths are the Helvetica widths to within half a percent, so the type sits where
# a Helvetica would; it is a TrueType face, and that is the part that matters here. The OpenType cut of
# the same design carries its outlines in CFF, which this matplotlib writes into the PDF while declaring
# it TrueType. Readers sniff the file and render it anyway, so nothing looks wrong, but the font
# dictionary in the submitted file is then a false statement about its own contents.
FONT = "Arimo"
plt.rcParams.update({
    "font.family": FONT, "font.size": PT_TICK,
    # A dollar-sign span is set by the maths engine, whose own default family is not the one above. Nothing in
    # the figure said so, and the tell is external: the saved file lists a second face. So every rho, times sign
    # and delta on these figures was a different typeface from the words beside it, and the mismatch grew as the
    # words moved to a Helvetica. Pointing all four maths families at the same face is what makes one figure one
    # typeface; the check on the built document reads the font list back and refuses a second family.
    "mathtext.fontset": "custom", "mathtext.rm": FONT, "mathtext.sf": FONT,
    "mathtext.it": f"{FONT}:italic", "mathtext.bf": f"{FONT}:bold",
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "pdf.fonttype": 42,
})


def main():
    os.makedirs(OUT, exist_ok=True)
    d = json.load(open(REJ))
    cal = json.load(open(CAL))
    c8 = json.load(open(C8))
    acc = list(cal["per_paper_composite"].values())
    acc_med = st.median(acc)
    papers = d["papers"]

    # Taller than the two-row version by about one typeset line, and no wider: panel (a) now carries
    # eleven rows instead of three, and the legend it grew past fits on one row now that it is anchored
    # to the figure rather than to the panel. The body has no free lines to give a figure, so the height
    # a panel costs is part of its design.
    # The left margin is set wide enough to hold panel (a)'s longest row label INSIDE the figure box, and
    # the canvas stays at the text width: the margin is a FRACTION of the canvas, so narrowing the canvas
    # to absorb an overhang narrows the label column too and the saved figure comes out wider still.
    # matplotlib reserves no room for tick labels, so with the default margin the label column hung off
    # the left edge, the tight bounding box grew to hold it, and the saved figure came out 5.79in wide --
    # a quarter inch over the text width, which md2tex.py would then place at its drawn size.
    fig, (axA, axB) = plt.subplots(
        1, 2, figsize=(5.5, 2.62),
        gridspec_kw={"width_ratios": [1.30, 1.0], "wspace": 0.40,
                     "left": 0.300, "right": 0.988, "top": 0.915, "bottom": 0.145})

    # ---- (a) the grade axis collapses ---------------------------------------------------------
    slots = c8["per_slot_grades"]
    # Slots ordered by how generous the slot is, so that what the panel is claiming -- that the spread
    # between the rows is the reviewer and not the paper -- is the thing the eye follows down the group.
    # An alphabetical order would bury it in eight labels.
    order = sorted(slots, key=lambda s_: c8["mean_recommendation_by_slot"][s_])
    disp = c8["slot_display"]
    # The effort tier is part of a slot's identity but not of this claim, and at this width it costs more
    # room than the model name it qualifies, so the label carries the model and Appendix H the tier.
    short = {k: v.rsplit(" ", 1)[0] if v.endswith((" High", " Max")) else v for k, v in disp.items()}

    rows = ([(y, d["grades"][k], lab) for y, (k, lab) in zip(Y_POP, ROWS)]
            + [(Y_SLOT0 + j, slots[s_], f"{s_}  {short[s_]}") for j, s_ in enumerate(order)])
    for y, dist, _ in rows:
        total = sum(dist.values())
        left = 0.0
        for g, c in zip(GRADES, GCOL):
            n = dist.get(g, 0)
            if not n:
                continue
            pct = 100.0 * n / total
            axA.barh(y, pct, left=left, color=c, height=0.66,
                     edgecolor="white", linewidth=0.5, zorder=2)
            # Label only segments with room. Contrast is measured where the text SITS, against its
            # own segment: the two dark ramp ends take white, the pale middle takes near-black.
            if pct >= 11:
                dark = c in ("#7f2704", "#d94801", "#08519c")
                axA.text(left + pct / 2, y, f"{n}", ha="center", va="center",
                         fontsize=PT_ANN, color="white" if dark else "#14181c",
                         fontweight="bold", zorder=3)
            left += pct
    axA.set_yticks([y for y, _, _ in rows])
    axA.set_yticklabels([lab for _, _, lab in rows], fontsize=PT_ANN)
    axA.set_xlim(0, 100)
    axA.set_ylim(Y_SLOT0 + len(order) - 0.4, Y_NOTE - 0.55)
    axA.set_xlabel("share of the row's reviews (%)", fontsize=PT_LAB)
    axA.set_title("a  the grade is the reviewer's", fontsize=PT_TITLE,
                  fontweight="bold", loc="left", pad=5)
    axA.tick_params(axis="x", labelsize=PT_TICK)
    axA.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axA.spines[s].set_visible(False)

    # The fact that carries the top group, stated on the panel and ABOVE the two rows it is about
    # rather than between them: at this row pitch a box in the gap would sit on the bars, and a white
    # box over data is the one annotation that can hide the thing it explains.
    axA.text(0, Y_NOTE, "same mode, same count — 110 of 160 in both",
             ha="left", va="center", fontsize=PT_ANN, color="#14181c", zorder=4)
    # The second group's header. The C-labels mean nothing on their own, and what they are is the claim:
    # a roster with no model in common with the instrument, over six vendors instead of two.
    # Every annotation on this panel is kept inside the axes width, which at 6.4 pt over 1.83in is about
    # forty-four characters. Two of them were three characters over and printed across panel (b)'s label.
    axA.text(0, Y_HEAD,
             f"second roster — {len(slots)} slots, "
             f"{len(set(c8['vendor_of_slot'].values()))} vendors, 32 each",
             ha="left", va="center", fontsize=PT_ANN, color="#3d474e", zorder=4)

    # The headline count rides in the legend label: the Accept segment is 0.6% of one bar and would
    # otherwise be invisible, which is exactly the finding and so must not be left to the eye.
    glab = dict(zip(GRADES, GRADES))
    glab["Accept"] = "Accept — 1 of 480, 16 of 256"
    # One row under the whole figure rather than two under one panel: the row the second version of this
    # legend saved is the row panel (a) grew into.
    fig.legend(handles=[Patch(facecolor=c, label=glab[g]) for g, c in zip(GRADES, GCOL)],
               loc="upper center", bbox_to_anchor=(0.5, 0.005), ncol=5, frameon=False,
               fontsize=PT_ANN, handlelength=1.1, handleheight=0.85,
               columnspacing=0.9, labelspacing=0.35, borderpad=0.0)

    # ---- (b) the composite axis orders --------------------------------------------------------
    axB.axhspan(min(acc), max(acc), color="#dfe6ec", zorder=0, lw=0)
    axB.axhline(acc_med, color="#5b6770", lw=0.7, ls=(0, (3.5, 2.2)), zorder=1)
    # Left side: above the median line the lower-rated arm has no points, so the label sits in
    # genuinely empty space instead of crowding the higher-rated cluster on the right.
    axB.text(0.02, acc_med, "accepted median", transform=axB.get_yaxis_transform(),
             ha="left", va="bottom", fontsize=PT_ANN, color="#3d474e")

    for arm, col, mk in (("high", "#08519c", "o"), ("low", "#d94801", "^")):
        xs = [p["human"] for p in papers if p["arm"] == arm]
        ys = [p["composite"] for p in papers if p["arm"] == arm]
        axB.scatter(xs, ys, s=17, c=col, marker=mk, linewidths=0.5,
                    edgecolors="white", zorder=3,
                    label=f"rejected, {'higher' if arm == 'high' else 'lower'}-rated")

    q1 = d["q1"]
    lo, hi = q1["spearman_ci"]
    axB.text(0.035, 0.975,
             f"across arms  ρ = {sgn(q1['spearman'])}  {rng(lo, hi)}",
             transform=axB.transAxes, ha="left", va="top", fontsize=PT_ANN,
             color="#14181c", zorder=4)
    # The within-arm figures are the honest qualifier: the pooled rho is earned partly by the gap
    # between two arms that were sampled at the rating scale's extremes, so each cluster carries its
    # own correlation, printed next to the cluster it describes.
    #
    # Computed from xs and ys -- the points this panel actually draws -- and not read from a key of
    # the analysis file. It used to read d["q0"]["within"], which is the composite against the HOUR
    # each paper was scored at, so the panel plotted the rating and annotated the clock. Nothing on
    # the page could reveal that: both quantities are within-arm Spearman coefficients over the same
    # sixteen papers, both are small, and the wrong one was the more convenient of the two. Deriving
    # the annotation from the plotted arrays is the only version of this that cannot come apart
    # again, which is why the correlation is recomputed here rather than looked up.
    #
    # Each cluster names itself, so panel (b) needs no legend competing for the same corner. The two
    # lines are STACKED, not side by side: at this type size the pair does not fit across a 1.9in
    # panel and silently overprinted when it was laid out horizontally.
    for arm, nm, col, y in (("low", "lower arm", "#d94801", 0.115),
                            ("high", "higher arm", "#08519c", 0.025)):
        xs = [p["human"] for p in papers if p["arm"] == arm]
        ys = [p["composite"] for p in papers if p["arm"] == arm]
        r, pv = spearman_p(ys, xs)
        axB.text(0.045, y, f"within {nm}  ρ = {sgn(r)} (p = {pv:.2f})",
                 transform=axB.transAxes, ha="left", va="bottom", fontsize=PT_ANN,
                 color=col, zorder=4)
    # The gap between the two arms is the design of the sample, and it is the one thing the panel draws
    # without naming: the corridor between the clusters is empty because the middle of the rating scale was
    # never sampled. Named in the corridor itself, which is the only part of the panel with no data in it,
    # and measured from the plotted ratings rather than read from a key, so a resample moves the label.
    x_lo = st.mean([p["human"] for p in papers if p["arm"] == "low"])
    x_hi = st.mean([p["human"] for p in papers if p["arm"] == "high"])
    gap = axB.text((max(p["human"] for p in papers if p["arm"] == "low")
                    + min(p["human"] for p in papers if p["arm"] == "high")) / 2,
                   (min(acc) + min(p["composite"] for p in papers)) / 2,
                   f"arm means\n{x_hi - x_lo:.3f} points apart",
                   ha="center", va="center", fontsize=PT_ANN, color="#3d474e",
                   linespacing=1.3, zorder=4)
    axB.set_xlabel("ICLR reviewers' mean rating", fontsize=PT_LAB)
    axB.set_ylabel("panel composite (z)", fontsize=PT_LAB)
    axB.set_title("b  the ranking is real, and coarse", fontsize=PT_TITLE, fontweight="bold",
                  loc="left", pad=5)
    axB.tick_params(labelsize=PT_TICK)
    for s in ("top", "right"):
        axB.spines[s].set_visible(False)
    # Headroom so the two cluster labels sit below their points rather than on them.
    ylo, yhi = axB.get_ylim()
    axB.set_ylim(ylo - 0.62 * (yhi - ylo) * 0.32, yhi)

    # The gap label sits between two clusters, so what has to hold is that it stays inside the corridor and
    # over nothing: a label that reaches either cluster is read as belonging to one arm, and one that touches
    # a point removes the observation it was placed beside.
    fig.canvas.draw()
    rnd = fig.canvas.get_renderer()
    e = gap.get_window_extent(rnd)
    inv = axB.transData.inverted()
    gx0 = inv.transform((e.x0, e.y0))[0]
    gx1 = inv.transform((e.x1, e.y1))[0]
    assert gx0 > max(p["human"] for p in papers if p["arm"] == "low"), gx0
    assert gx1 < min(p["human"] for p in papers if p["arm"] == "high"), gx1
    over = [(p["human"], p["composite"]) for p in papers
            if e.contains(*axB.transData.transform((p["human"], p["composite"])))]
    assert not over, f"the arm-gap label covers {over}"
    for t in axB.texts:
        if t is not gap:
            assert not e.overlaps(t.get_window_extent(rnd)), f"the arm-gap label covers {t.get_text()!r}"

    fig.savefig(f"{OUT}/F1.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F1.png", dpi=400, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F1.pdf and F1.png")

    # ---- what the panels assert, printed so the caption can be checked against it -------------
    print(f"(a) Major Revision: accepted {d['grades']['accepted_ref']['Major Revision']}/160, "
          f"rejected-high {d['grades']['rejected_high']['Major Revision']}/160")
    print(f"    Accept total across all 480: "
          f"{sum(d['grades'][k].get('Accept', 0) for k in d['grades'])}")
    print(f"    R&R ladder 11/32/80 check: "
          f"{[d['grades'][k]['Reject and Resubmit'] for k, _ in ROWS]}")
    acc_by = {s_: r["Accept"] for s_, r in slots.items() if r.get("Accept")}
    rr = max(slots, key=lambda s_: slots[s_]["Reject and Resubmit"])
    print(f"    second roster: {len(slots)} slots over "
          f"{len(set(c8['vendor_of_slot'].values()))} vendors, "
          f"{sum(sum(r.values()) for r in slots.values())} reviews, 32 each; order {order}")
    print(f"    Accept {sum(acc_by.values())} of the 256, from {acc_by}; "
          f"{rr} R&R {slots[rr]['Reject and Resubmit']}/32; modal grade "
          f"{max(GRADES, key=lambda g: sum(r.get(g, 0) for r in slots.values()))}")
    print(f"(b) accepted band [{min(acc):+.3f}, {max(acc):+.3f}], median {acc_med:+.3f}; "
          f"rejected median {st.median([p['composite'] for p in papers]):+.3f}")
    print(f"    arm mean ratings {x_lo:.3f} and {x_hi:.3f}, {x_hi - x_lo:.3f} apart, with no paper rated "
          f"between {max(p['human'] for p in papers if p['arm'] == 'low'):.1f} and "
          f"{min(p['human'] for p in papers if p['arm'] == 'high'):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""F2: where the ranking signal goes, and what aggregating five models buys.

(a) The four-population ladder. As the population becomes more homogeneous -- i.e. as it comes to
    look like the set a programme committee actually decides over -- the paper's own contribution to
    score variance falls (64.5% -> 39.1%) while the reviewer slot's contribution roughly doubles
    (8.4% -> 18.8%). The instrument does not degrade gracefully: it loses discriminating power in
    exactly the regime the decision lives in. Independent corroboration of F1(b), which measures the
    same collapse as a correlation rather than as a variance share.

(b) The aggregation null. Each slot alone, scored identically, with its own bootstrap interval, and
    the 5-model panel on the same axis. The panel sits INSIDE the range its members span and BELOW
    its best member. This is a null claim, so it is drawn with intervals and stated against the MEAN
    member: panel - best is upward-biased by selection (max of five) and is reported as a bound.

Drawn at final placed size (5.5in = NeurIPS text width).
"""
from __future__ import annotations

import json
import os

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import rng, sgn  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

WS = "/path/to/workspace"
AN = f"{WS}/ai_native_academia"
OUT = f"{AN}/figs"

# Population order is the ladder itself, and it is the order variance_decomp.json and Appendix C's table
# both use: proximity to the set a programme committee decides over. This list had the middle two rungs the
# other way round, which is not a cosmetic difference -- the body says the reviewer-to-paper ratio "rises
# monotonically" and points here, and in the swapped order it runs 0.130, 0.233, 0.204, 0.482 and does not.
LADDER = [
    ("ICLR rejected, all 32 (heterogeneous)", "rejected 32\nmixed quality"),
    (".. low-rated 16 only", "rejected 16\nlower-rated"),
    (".. high-rated 16 only", "rejected 16\nhigher-rated"),
    ("ICLR accepted 16 (homogeneous)", "accepted 16\nhomogeneous"),
]
SLOT_LAB = {"R1": "R1  gpt-5.5", "R2": "R2  gpt-5.4", "R3": "R3  opus-4.8",
            "R4": "R4  opus-4.7", "R5": "R5  sonnet-4.6"}
C_PAPER, C_SLOT, C_RESID = "#08519c", "#d94801", "#d9dee3"
RATIO_X = 117           # right edge of panel (a)'s ratio column, in the same units as the bars
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


def resolve(vd):
    """Match the ladder to variance_decomp.json's keys without hardcoding their exact spelling."""
    out = []
    for want, label in LADDER:
        hit = next((k for k in vd if k == want), None)
        if hit is None:  # keys carry a "..." prefix in some runs; fall back to a token match
            toks = [t for t in want.replace(",", " ").split() if t not in ("only", "ICLR")]
            hit = next((k for k in vd if all(t in k for t in toks)), None)
        if hit is None:
            raise SystemExit(f"F2: no variance_decomp key matches {want!r}; keys={list(vd)}")
        out.append((hit, label))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    vd = json.load(open(f"{AN}/reject_arm/variance_decomp.json"))
    cf = json.load(open(f"{AN}/confounds.json"))
    rows = resolve(vd)

    fig, (axA, axB) = plt.subplots(
        1, 2, figsize=(5.5, 2.30), gridspec_kw={"width_ratios": [1.15, 1.0], "wspace": 0.52})

    # ---- (a) the ladder -----------------------------------------------------------------------
    for i, (key, label) in enumerate(rows):
        v = vd[key]
        left = 0.0
        for pct, col in ((v["paper_pct"], C_PAPER), (v["slot_pct"], C_SLOT),
                         (v["resid_pct"], C_RESID)):
            axA.barh(i, pct, left=left, color=col, height=0.6, edgecolor="white",
                     linewidth=0.5, zorder=2)
            # 5% is ~15pt of bar at this width, ample for a 1-2 digit label. A 12% threshold left the
            # 8% and 11% reviewer segments blank, which hid half the panel's message (8 -> 19).
            if pct >= 5:
                axA.text(left + pct / 2, i, f"{pct:.0f}", ha="center", va="center",
                         fontsize=PT_ANN, fontweight="bold", zorder=3,
                         color="white" if col in (C_PAPER, C_SLOT) else "#14181c")
            left += pct
    axA.set_yticks(range(len(rows)))
    axA.set_yticklabels([l for _, l in rows], fontsize=PT_TICK, linespacing=1.15)
    axA.invert_yaxis()
    # The bars run to 100 and the axis to RATIO_X, which leaves a column for the ratio inside the plotting
    # area. Right-aligning it at 100 instead overprinted the residual segment's own percentage on three of
    # the four rows, and widening the gap between the panels would have taken the space from panel (b)'s
    # slot labels, which are already against it.
    axA.set_xlim(0, RATIO_X + 1)
    axA.set_xticks([0, 20, 40, 60, 80, 100])
    axA.set_xlabel("share of score variance (%)", fontsize=PT_LAB)
    axA.set_title("a  the signal thins where the decision is",
                  fontsize=PT_TITLE, fontweight="bold", loc="left", pad=5)
    for s in ("top", "right", "left"):
        axA.spines[s].set_visible(False)
    axA.legend(handles=[Patch(facecolor=C_PAPER, label="the paper"),
                        Patch(facecolor=C_SLOT, label="which reviewer"),
                        Patch(facecolor=C_RESID, label="residual")],
               loc="upper center", bbox_to_anchor=(0.5, -0.29), ncol=3, frameon=False,
               fontsize=PT_ANN, handlelength=1.1, handleheight=0.85, columnspacing=1.1,
               borderpad=0.0)

    # The reviewer-to-paper ratio, right-aligned at the end of each bar. A connected spine through
    # paper_pct was drawn here instead, and it tapered cleanly only because the rungs were in the wrong
    # order: in the right one paper_pct runs 64.5, 52.5, 59.0, 39.1, and the body says so in as many
    # words -- "the paper's own share does not fall monotonically across those rungs". Drawing a monotone
    # trend through a non-monotone quantity is the panel arguing against its own text. The ratio is what
    # orders the ladder, it is monotone, and Appendix C's table prints these same four values.
    # An unlabelled column of numbers is not a result, so it gets the header Appendix C's table uses for the
    # same quantity, in the row of empty space above the first bar.
    for i, (key, _) in enumerate(rows):
        axA.text(RATIO_X, i, f"{vd[key]['ratio']:.2f}×", ha="right", va="center",
                 fontsize=PT_ANN, color="#14181c", zorder=3)
    axA.text(RATIO_X, -0.62, "reviewer / paper", ha="right", va="center", fontsize=PT_ANN,
             color="#5a646d", zorder=3)
    axA.set_ylim(len(rows) - 0.45, -0.95)

    # ---- (b) the aggregation null -------------------------------------------------------------
    solo, cis = cf["slot_alone"], cf["slot_alone_ci"]
    order = list(SLOT_LAB)
    ys = list(range(len(order)))
    for y, s in zip(ys, order):
        lo, hi = cis[s]
        r = solo[s]["rho"]
        axB.plot([lo, hi], [y, y], color="#8c99a4", lw=0.9, zorder=2,
                 solid_capstyle="butt")
        axB.scatter([r], [y], s=17, c="#3d474e", zorder=3, linewidths=0)
    axB.set_yticks(ys)
    axB.set_yticklabels([SLOT_LAB[s] for s in order], fontsize=PT_TICK)
    axB.invert_yaxis()

    prho = cf["full"]["rho"]
    plo, phi = cf["panel_ci"]
    yp = len(order) + 0.35
    axB.plot([plo, phi], [yp, yp], color="#08519c", lw=1.4, zorder=4, solid_capstyle="butt")
    axB.scatter([prho], [yp], s=30, c="#08519c", marker="D", zorder=5, linewidths=0)
    axB.axvline(prho, color="#08519c", lw=0.6, ls=(0, (3, 2.4)), zorder=1)
    axB.set_yticks(ys + [yp])
    axB.set_yticklabels([SLOT_LAB[s] for s in order] + ["5-model panel"], fontsize=PT_TICK)
    for t, s in zip(axB.get_yticklabels(), order + ["panel"]):
        if s == "panel":
            t.set_color("#08519c")
            t.set_fontweight("bold")

    b = cf["boot"]
    dm, dmc = b["d_mean_solo"], b["d_mean_solo_ci"]
    db, dbc = b["d_best_solo"], b["d_best_solo_ci"]
    # Two nulls in the units of the panel above, each a difference with its own interval: what a fifth
    # reviewer buys over the average member, and what it buys over the best one. Printed rather than left to
    # the caption because an eye cannot read a difference of correlations off two overlapping intervals.
    axB.text(0.5, -0.26,
             f"panel − mean member  {sgn(dm, 3)}  {rng(dmc[0], dmc[1], 3)}\n"
             f"panel − best member  {sgn(db, 3)}  {rng(dbc[0], dbc[1], 3)}",
             transform=axB.transAxes, ha="center", va="top", fontsize=PT_ANN,
             color="#14181c", linespacing=1.3)
    axB.set_xlabel("ρ with ICLR reviewers' mean rating", fontsize=PT_LAB)
    axB.set_title("b  what averaging five models buys", fontsize=PT_TITLE,
                  fontweight="bold", loc="left", pad=5)
    axB.set_ylim(yp + 0.7, -0.7)
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)
    axB.tick_params(axis="y", length=0)

    fig.savefig(f"{OUT}/F2.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F2.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F2.pdf and F2.png")

    print("(a) paper%: " + " -> ".join(f"{vd[k]['paper_pct']:.1f}" for k, _ in rows))
    print("    slot%:  " + " -> ".join(f"{vd[k]['slot_pct']:.1f}" for k, _ in rows))
    # The panel's ordering claim, checked rather than asserted: the ratio must rise across the four rungs,
    # and the paper share must be allowed not to. Reversing two rungs made the second one look monotone too.
    rat = [vd[k]["ratio"] for k, _ in rows]
    print("    ratio:  " + " -> ".join(f"{r:.3f}" for r in rat)
          + f"   monotone: {all(b > a for a, b in zip(rat, rat[1:]))}")
    print(f"(b) solo rho range [{min(solo[s]['rho'] for s in order):+.3f}, "
          f"{max(solo[s]['rho'] for s in order):+.3f}], panel {prho:+.3f} "
          f"-> panel inside member range: "
          f"{min(solo[s]['rho'] for s in order) < prho < max(solo[s]['rho'] for s in order)}")
    print(f"    panel-mean CI includes 0: {dmc[0] < 0 < dmc[1]}; "
          f"panel-best CI includes 0: {dbc[0] < 0 < dbc[1]}")
    for key, lab in grade_rows:
        ci = go["rho_vs_venue_rating_ci"][key]
        gap = go[f"rho_gap_{'grade_minus' if key == 'grade_mean' else 'bar_share_minus'}_composite"]
        print(f"    {lab}: rho {go['rho_vs_venue_rating'][key]:+.3f} "
              f"[{ci['low']:+.3f}, {ci['high']:+.3f}], minus composite {gap['point']:+.3f} "
              f"[{gap['ci'][0]:+.3f}, {gap['ci'][1]:+.3f}] -> includes 0: "
              f"{gap['ci'][0] < 0 < gap['ci'][1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

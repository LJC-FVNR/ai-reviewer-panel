#!/usr/bin/env python3
"""F3: what a semantics-preserving edit costs, and what the grade can see of it.

Panel (a). The criterion is a comparison, not a threshold at zero: an edit counts as moving the score
only if it moves it more than re-running the same panel on unchanged text does. Two pre-registered
reference bands are drawn behind the points.

  +/- 0.160 z   the panel's own test-retest band (|panel1 - panel2| on identical text)
  +/- 0.115 z   the median gap between adjacent papers in the reference field

One of the three arms clears the narrower band and separates from its null: joining adjacent sentences,
at -0.138 z on 38 of 47 papers. Relocating figures to end matter does not, at -0.020 z on a 24/23 split.
T2 is drawn in grey and set apart because it is NOT a presentation transform -- it rewrites claim
strength, so a reviewer scoring it differently may be updating rationally rather than reacting to
presentation. It is kept as the arm the panel is supposed to notice.

Panel (b) is the grade axis, and the reason it had to be measured separately. Each quantity is divided
by its OWN re-run movement, which is what makes a z-average over twelve channels and a single draw from
a five-rung ladder comparable at all:

  composite   median |Delta| over papers  /  0.160 z, the pre-registered re-run band
  grade       mean |step| over reviewer cells  /  the mean |step| between two readings of unchanged
              text by the same slot, 0.171 rungs

The two lanes come out on opposite sides of 1.0. The composite's spread sits at 0.76 to 0.98 of the
re-run band, and every arm's grade moves MORE than a re-run of the same panel does -- 1.05, 1.12 and
1.26 -- with per-reviewer agreement under each arm below the re-run's 0.829. So the grade does not
separate an edit from a second reading in either direction, which is a statement about the coarseness
of a five-rung ladder and not about the edits being cheap.

Both panels are one roster and one paper set: the five-slot panel over all forty-eight papers, every
contrast taken inside a single sitting. The vendor-diversity roster is not drawn here. It covers eight
of the forty-eight papers, and putting it on a shared axis is how a difference between two paper sets
gets read as a difference between two panels; the like-for-like reading of the two rosters is a table
in the appendix, where the paper set can be named. Its grade lane in particular counts a different
event -- one variant panel against two baselines, rather than panel against panel -- so no axis here
is shared with it.

Reads pooled_analysis.json (pooled_analyze.py) alone, so figure and prose quote one computation.
Refuses to draw if the claim in either title fails.
Drawn at final placed size, and included in the paper at this PDF's natural width, so 1pt here is 1pt
on the page.
"""
from __future__ import annotations

import json
import os

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import sgn  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

WS = "/path/to/workspace"
AN = f"{WS}/ai_native_academia"
OUT, RES = f"{AN}/figs", f"{AN}/pooled_analysis.json"

ORDER = ["T1_endmatter", "T2_concede", "T3_lengthen"]
# Named as fig8 and the body name them. `soften the claims` said something the arm does not do: T2 also
# withdraws a significance claim outright, and a reader who meets it as softening here and as a withdrawal
# there has to work out whether the two figures are reporting the same arm.
NICE = {"T1_endmatter": "T1\nfigures to\nend matter",
        "T2_concede": "T2\na claim\nwithdrawn",
        "T3_lengthen": "T3\njoin\nsentences"}
COL = {"T1_endmatter": "#08519c", "T2_concede": "#9aa5ae", "T3_lengthen": "#3f7f3f"}
# Fixed by what each arm edits, before any scoring, and not by how it behaved. T2 rewrites how strongly
# the paper states its own findings, so a score that follows it is not evidence of a presentation effect.
CLAIM_EDIT = {"T2_concede"}
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
    if not os.path.exists(RES):
        raise SystemExit(f"F3: {RES} missing -- run pooled_analyze.py first")
    os.makedirs(OUT, exist_ok=True)
    P = json.load(open(RES))
    band, gap = P["band_rerun_preregistered"], P["band_adjacent_preregistered"]
    arms = P["arms"]
    names = [t for t in ORDER if t in arms and arms[t].get("pooled")]
    if len(names) != len(ORDER):
        raise SystemExit(f"F3: {sorted(set(ORDER) - set(names))} has no pooled reading; the panel would "
                         f"compare a corpus with a subset of itself")

    # wspace is generous because panel (b) carries a y-axis LABEL on its left. At 0.10 (tuned for an
    # earlier panel (b) that had right-side ticks and no label) that label rendered on top of panel
    # (a)'s data points and ate its "one rank" annotation.
    # wspace is generous twice over: panel (b) carries its values in its y tick labels, so its labels
    # reach left into the gap, and panel (a)'s deepest x tick label ("...join sentences / -0.138 /
    # 38/9 down/up") reaches right into it. At 0.42 the two came within 0.02in of touching.
    fig, (axA, axB) = plt.subplots(
        1, 2, figsize=(5.5, 2.6), gridspec_kw={"width_ratios": [1.0, 1.0], "wspace": 0.54})

    # ---- (a) Delta composite against the panel's own noise ------------------------------------
    axA.axhspan(-band, band, color="#e3e8ed", zorder=0, lw=0)
    axA.axhspan(-gap, gap, color="#c9d4de", zorder=0, lw=0)
    axA.axhline(0, color="#5b6770", lw=0.6, zorder=1)

    # The title is a claim about how many arms move, so it is settled from the data before anything is
    # drawn. A figure that keeps its title after the data stops supporting it is the worst artifact
    # here, because it is the one a reader trusts without checking. Both conjuncts are the section's:
    # clearing the narrower band, and separating from the sign null.
    moved = [t for t in names
             if abs(arms[t]["pooled"]["median"]) > gap and arms[t]["pooled"]["sign_p"] < 0.05]
    if len(moved) != 1:
        raise SystemExit("F3(a) refuses to draw: its title says one arm of three moves the composite, "
                         f"and {len(moved)} do ({', '.join(moved) or 'none'})")

    for i, t in enumerate(names):
        r = arms[t]["pooled"]
        d = list(arms[t]["per_paper"].values())
        xs = [i + (-0.17 + 0.34 * (k / max(1, len(d) - 1))) for k in range(len(d))]
        axA.scatter(xs, d, s=15, c=COL[t], zorder=3, linewidths=0.5, edgecolors="white")
        axA.plot([i - 0.30, i + 0.30], [r["median"], r["median"]], color=COL[t], lw=1.7, zorder=4,
                 solid_capstyle="butt")
        axA.plot([i, i], r["ci95"], color=COL[t], lw=0.9, zorder=2, solid_capstyle="butt")
    # Value and split ride IN the tick label. Placed below the lowest point they overprinted the
    # tick labels, and any y-relative position is one outlier away from doing it again.
    # The third line used to be a PASS or a FAIL against the criterion. It is now the split of papers,
    # because the criterion bounds spread across papers rather than a shift and all three arms fail it
    # including the one that moves nothing -- so a verdict in a tick label was the one number on this
    # figure that could not be read as it was meant.
    # Written in the paper's own sign convention rather than as "24/23 down/up", which at thirteen
    # characters was wider than the 0.58in a tick owns and overprinted both its neighbours.
    ticks = [f"{NICE[t]}\n{sgn(arms[t]['pooled']['median'], 3)}\n"
             f"{arms[t]['pooled']['negative']}\u2212/{arms[t]['pooled']['positive']}+" for t in names]

    axA.set_xticks(range(len(names)))
    axA.set_xticklabels(ticks, fontsize=PT_TICK, linespacing=1.25)
    for lab, t in zip(axA.get_xticklabels(), names):
        lab.set_color(COL[t])
    axA.set_xlim(-0.55, len(names) - 0.45)
    axA.set_ylabel("Δ composite (z)", fontsize=PT_LAB)
    axA.set_title("a  one edit of three moves the composite",
                  fontsize=PT_TITLE, fontweight="bold", loc="left", pad=13)
    for s in ("top", "right"):
        axA.spines[s].set_visible(False)
    # The bands are named in a legend, not inline. Inline, "one rank +/-0.115" sat at y=-0.127 and was
    # drawn OVER three of T2's data points -- an annotation occluding the data it describes. The
    # upper-right corner is the one region with no points in it (every transform's positive outliers
    # are T1's, at the left), so the legend cannot cover a dot.
    # Swatches carry a thin edge: #e3e8ed on the white legend card was very nearly white-on-white, so
    # the key identifying the WIDER band -- the one the verdict is measured against -- was invisible.
    leg = axA.legend(handles=[Patch(facecolor="#e3e8ed", edgecolor="#8c99a4", linewidth=0.5,
                                    label=f"re-run noise \u00b1{band:.3f}"),
                              Patch(facecolor="#c9d4de", edgecolor="#8c99a4", linewidth=0.5,
                                    label=f"one rank \u00b1{gap:.3f}")],
                     loc="upper right", frameon=True, facecolor="white", edgecolor="none",
                     framealpha=0.93, fontsize=PT_ANN, handlelength=1.0, handleheight=0.8,
                     borderpad=0.35, labelspacing=0.3)
    # The corner with no data in it is still the right corner, and on this corpus it has no room: T2's
    # highest papers reach +0.27 and the card's lower edge landed within four points of them. So the top
    # of the range is expanded until the card clears every point, measured off the drawn legend rather
    # than set to a number that was right for one reading of the corpus.
    pts = [v for t in names for v in arms[t]["per_paper"].values()]
    for _ in range(12):
        fig.canvas.draw()
        box = leg.get_window_extent().transformed(axA.transData.inverted())
        hit = [v for v in pts if v > box.y0]
        if not hit:
            break
        lo, hi = axA.get_ylim()
        axA.set_ylim(lo, hi + (max(hit) - box.y0) + 0.06 * (hi - lo))
    else:
        raise SystemExit("F3(a): the band legend will not clear the data in this corner")

    # ---- (b) each quantity in units of ITS OWN re-run movement --------------------------------
    # Dividing by the same quantity's own test-retest movement is what lets a twelve-channel z-average
    # and a single draw from a five-rung ladder share one axis. 1.0 = "moved exactly as much as
    # re-running this panel on unchanged text".
    U = {"composite": [arms[t]["pooled"]["median_abs"] / band for t in names],
         "grade": [arms[t]["grade_cells"]["mean_step"] / arms[t]["grade_cells"]["mean_step_rerun"]
                   for t in names]}
    AGREE = [(arms[t]["grade_cells"]["agreement"], arms[t]["grade_cells"]["agreement_rerun"])
             for t in names]

    # Two conjuncts, both of them orderings rather than tolerances: the grade lane is entirely above the
    # re-run line, the composite lane entirely on or below it, and each arm's per-reviewer agreement is
    # below the re-run's. Nothing here is a threshold anyone chose.
    bad = [f"{t} grade {U['grade'][i]:.2f}x" for i, t in enumerate(names) if U["grade"][i] < 1.0]
    bad += [f"{t} composite {U['composite'][i]:.2f}x" for i, t in enumerate(names)
            if U["composite"][i] > 1.0]
    bad += [f"{t} agreement {a:.4f} >= re-run {b:.4f}" for t, (a, b) in zip(names, AGREE) if a >= b]
    if bad:
        raise SystemExit("F3(b) refuses to draw: its title says the grade cannot separate an edit from "
                         "a re-run while the composite's spread stays inside the band. Violations: "
                         + "; ".join(bad))

    # Rows run in two lanes, composite above grade, so the panel is read as one comparison per lane
    # rather than six markers. Colour is the quantity: with two series, giving each arm its own colour
    # made the legend the largest object in the panel.
    LANES = [("composite", "composite (z)", "#08519c"), ("grade", "grade (5 rungs)", "#d94801")]
    STEP, GAP = 0.9, 0.75
    ypos, head, y = {}, {}, 0.0
    for q, _, _ in LANES:
        head[q] = y - STEP
        for i in range(len(names)):
            ypos[(q, i)] = y
            y += STEP
        y += GAP
    tr = blended_transform_factory(axB.transAxes, axB.transData)

    axB.axvspan(0, 1.0, color="#eef1f4", zorder=0, lw=0)
    axB.axvline(1.0, color="#14181c", lw=0.9, zorder=1)
    for q, qlab, col in LANES:
        for i, t in enumerate(names):
            yy, v = ypos[(q, i)], U[q][i]
            # A stem to the reference line, not a bar from zero: the reading is the distance from 1.0
            # and its side, and a bar from the origin makes 0.76 and 1.26 look like a small difference
            # in length rather than opposite answers.
            axB.plot([1.0, v], [yy, yy], color=col, lw=0.9, zorder=2, solid_capstyle="butt",
                     alpha=0.55)
            axB.scatter([v], [yy], s=21, c=col, zorder=4, linewidths=0)
        axB.text(0.02, head[q], qlab, transform=tr, ha="left", va="center", fontsize=PT_ANN,
                 fontweight="bold", color=col)

    # Values ride IN the tick labels, as in panel (a). Placed at the markers they overprinted each
    # other where two arms nearly coincide, and a fixed label column on the right would have cost a
    # third of the panel's width.
    ticks, tlab = [], []
    for q, _, _ in LANES:
        for i, t in enumerate(names):
            ticks.append(ypos[(q, i)])
            tlab.append(f"{NICE[t].split(chr(10))[0]}   {U[q][i]:.2f}")
    axB.set_yticks(ticks)
    axB.set_yticklabels(tlab, fontsize=PT_TICK)
    # T2 is greyed in the LABEL rather than in the marker: it is excluded from the verdict for what it
    # edits, not for where it landed, and greying its data would hide that it lands with the other two.
    for lab, t in zip(axB.get_yticklabels(), [t for _, _, _ in LANES for t in names]):
        if t in CLAIM_EDIT:
            lab.set_color("#5b6770")
    axB.set_ylim(y - GAP - STEP / 2, head["composite"] - STEP / 2)
    axB.set_xlim(0, max(v for vs in U.values() for v in vs) * 1.13)
    axB.set_xlabel("movement / its own re-run", fontsize=PT_LAB)
    axB.set_title("b  the grade cannot tell an edit from a re-run",
                  fontsize=PT_TITLE, fontweight="bold", loc="left", pad=13)
    # Shortened from "moved as much as": at 44 characters this line was wider than its own axes and
    # set the figure's right-hand bbox, so the placed figure carried a strip of empty paper.
    axB.text(0.0, 1.008, "1.0 = as much as re-running the panel", transform=axB.transAxes,
             ha="left", va="bottom", fontsize=PT_ANN, color="#3d474e")
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)
    axB.tick_params(axis="y", length=0)
    # Ticks are set explicitly so the 1.0 reference can be emphasised; reading them back off the
    # autolocator before a draw returns empty strings.
    xt = [v / 2 for v in range(0, int(axB.get_xlim()[1] * 2) + 1)]
    axB.set_xticks(xt)
    axB.set_xticklabels([f"{v:.1f}" for v in xt], fontsize=PT_TICK)
    for lab, v in zip(axB.get_xticklabels(), xt):
        if abs(v - 1.0) < 1e-9:
            lab.set_fontweight("bold")

    fig.savefig(f"{OUT}/F3.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F3.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F3.pdf and F3.png")

    print(f"bands: re-run +/-{band:.4f}, one rank +/-{gap:.4f} -> noise band wider: {band > gap}")
    for t in names:
        r = arms[t]["pooled"]
        print(f"  {t}: n {r['n']} median {r['median']:+.4f} |med| {r['median_abs']:.4f} "
              f"CI {r['ci95']} sign {r['negative']}-/{r['positive']}+ p {r['sign_p']:.4f}"
              f"{'  <- clears one rank and its null' if t in moved else ''}")
    print("(b) in units of its own re-run movement:")
    for i, t in enumerate(names):
        a, b = AGREE[i]
        print(f"  {t}: composite {U['composite'][i]:.2f}x  grade {U['grade'][i]:.2f}x  "
              f"per-cell agreement {a:.4f} against the re-run's {b:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

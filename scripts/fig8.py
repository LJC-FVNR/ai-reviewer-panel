#!/usr/bin/env python3
"""F8: what each edit moved, channel by channel, as the body's own exhibit for the presentation section.

The section this figure belongs to had no figure. Its result reached a reader as a composite number and a
ratio, and the composite is an average over twelve channels, so the one thing the average cannot show is the
only thing that separates the two arms: whether the panel moved because it re-read the paper's claims or
because it re-read the paper's sentences.

Three rows, twelve channels each, on one signed scale.

  T1  figures relocated to end matter    six channels down, five up, none of them far
  T2  a claim of significance withdrawn  eight up and four down, and the two extremes are the ones a
                                         reviewer should move: how honestly the paper states its evidence
                                         rises, how well it is organised falls
  T3  adjacent sentences joined          every channel that moved, moved down

That last row is the paper's claim about presentation, drawn rather than summarised: an edit that changed no
claim, no number and no result did not produce a judgement about anything in particular, it produced a
uniform penalty. The row above it is what a judgement looks like on the same instrument, and it is why the
composite for T2 comes out near zero -- not because the panel missed the edit, but because it charged the
paper on one channel and credited it on another. A reader who sees only the composite reads that arm as a
null.

The distinction between the two is settled before anything is drawn, and the title states it: T2 divides the
channels, T3 lowers every one it moves. Both halves are asserted against the data below, and the figure
refuses to draw if either fails.

Marker fill carries the allotment, the same convention F4 uses at full detail: a filled dot is a channel that
edit cannot legitimately move, an open dot one it may. T2's row is nearly all open because withdrawing a
claim of significance is licensed to move almost everything -- that is what makes it the control for T3.

Reads pia_null.json for the per-channel medians, the same file and roster F4 draws, so the body's digest and
the appendix's full version cannot disagree; and pooled_analysis.json for each arm's composite, so the row
labels quote the same computation the prose does. Five-slot roster, all forty-eight papers, every contrast
taken inside one sitting.

Drawn at final placed size, and included in the paper at this PDF's natural width, so 1pt here is 1pt on the
page.
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

WS = "/path/to/workspace"
AN = f"{WS}/ai_native_academia"
OUT = f"{AN}/figs"
NULL = f"{AN}/pia_null.json"
RES = f"{AN}/pooled_analysis.json"
ROSTER = "5model_pooled"

ORDER = ["T1_endmatter", "T2_concede", "T3_lengthen"]
NICE = {"T1_endmatter": "T1  figures to end matter",
        "T2_concede": "T2  a claim withdrawn",
        "T3_lengthen": "T3  sentences joined"}
# fig3's hues for the same three arms, so a reader who has seen one figure reads the other's rows without
# relearning them.
COL = {"T1_endmatter": "#08519c", "T2_concede": "#6b7681", "T3_lengthen": "#3f7f3f"}
SHORT = {"significance": "significance", "novelty": "novelty", "rigor": "rigor",
         "statistical_soundness": "statistical soundness", "calibration_honesty": "calibration honesty",
         "clarity": "clarity", "structure_compliance": "structure compliance",
         "reproducibility": "reproducibility", "related_work": "related work",
         "figure_quality": "figure quality", "breadth_generality": "breadth / generality",
         "overall_recommendation": "overall recommendation"}
# The channels each edit is licensed to reach, imported rather than retyped: the allotment is a claim the
# paper makes in four places and a fifth copy here could disagree with the figure it sits beside. Imported off
# this file's own directory, the way the other figure scripts do it, so the bundle's copy resolves against the
# bundle's copy of analyse_n1 rather than against a path that exists only here.
import analyse_n1                                                        # noqa: E402
LEGIT = analyse_n1.LEGITIMATE

WIDTH_IN = 5.5
PT_TITLE, PT_LAB, PT_TICK, PT_ANN = 8.0, 7.5, 7.0, 6.4
# The grotesque the figure guidelines of this literature ask for, in the one flavour of it that embeds
# correctly. Its advance widths are the Helvetica widths to within half a percent, so the type sits where
# a Helvetica would; it is a TrueType face, and that is the part that matters here. The OpenType cut of
# the same design carries its outlines in CFF, which this matplotlib writes into the PDF while declaring
# it TrueType.
FONT = "Arimo"
plt.rcParams.update({
    "font.family": FONT, "font.size": PT_TICK,
    "mathtext.fontset": "custom", "mathtext.rm": FONT, "mathtext.sf": FONT,
    "mathtext.it": f"{FONT}:italic", "mathtext.bf": f"{FONT}:bold",
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "pdf.fonttype": 42,
})


MS, MEW = 3.6, 0.9        # marker diameter and edge, in points; the dodge below is measured against them
ROW_GAP = 1.3             # rows further apart than the labels reach, so a label belongs to one row


def dodge(vals, min_sep, levels):
    """-> {channel: vertical offset within its row}, so twelve channels are drawn as twelve dots.

    Two of the arms put most of their twelve inside a tenth of a z of each other and one arm has two channels
    at exactly zero, so a single line per row draws seven or eight dots for twelve channels and the row's own
    count contradicts what is on the page. The offsets are vertical, which is the axis that carries no
    quantity here: a row is a category, and a dot's height inside it means nothing at all.
    """
    placed, out = [], {}
    for m, v in sorted(vals.items(), key=lambda kv: kv[1]):
        for off in levels:
            if all(abs(v - pv) >= min_sep or abs(off - po) > 0.01 for pv, po in placed):
                out[m], _ = off, placed.append((v, off))
                break
        else:
            raise SystemExit(f"F8: {m} at {v:+.4f} has no free rung; the row would draw fewer dots than "
                             f"channels")
    return out


def channels(pn, t):
    """-> {channel: median delta}, from the single-channel axes, which is where the per-channel median is."""
    d = {a["axis"]: a["delta"] for a in pn[t]["axes"] if a["n_channels"] == 1 and a["axis"] in SHORT}
    if len(d) != len(SHORT):
        raise SystemExit(f"F8: {t} carries {len(d)} of {len(SHORT)} channels; a row would be missing one")
    return d


def main():
    for f in (NULL, RES):
        if not os.path.exists(f):
            raise SystemExit(f"F8: {f} missing -- run pia_null.py and pooled_analyze.py first")
    os.makedirs(OUT, exist_ok=True)
    pn = json.load(open(NULL))["rosters"][ROSTER]["transforms"]
    arms = json.load(open(RES))["arms"]
    for t in ORDER:
        if t not in pn or not arms.get(t, {}).get("pooled"):
            raise SystemExit(f"F8: {t} has no pooled reading on {ROSTER}")
    D = {t: channels(pn, t) for t in ORDER}
    up = {t: [m for m, v in D[t].items() if v > 0] for t in ORDER}
    dn = {t: [m for m, v in D[t].items() if v < 0] for t in ORDER}

    # The title's two halves, settled from the data before anything is drawn. A figure that keeps its title
    # after the data stops supporting it is the worst artifact here, because it is the one a reader trusts
    # without checking.
    #
    # "Divides the channels" has to be more than twelve jitters that happen to straddle zero, and the test
    # for that is already in the file: each single channel carries its own matched null, and the two
    # channels this figure names are the two the pipeline itself reports as having separated from it. So the
    # check is that the arm's extremes are the named pair, that they point opposite ways, and that each
    # carries the file's own verdict rather than a threshold invented here. "Lowers every one it moves" is
    # a count of zero and needs no test.
    verdict = {t: {a["axis"]: a for a in pn[t]["axes"] if a["n_channels"] == 1} for t in ORDER}
    bad = []
    T2, T3 = "T2_concede", "T3_lengthen"
    hi2, lo2 = max(D[T2], key=lambda m: D[T2][m]), min(D[T2], key=lambda m: D[T2][m])
    if (hi2, lo2) != ("calibration_honesty", "structure_compliance"):
        bad.append(f"T2's extremes are {hi2} and {lo2}, not the pair the figure labels")
    if not up[T2] or not dn[T2]:
        bad.append(f"T2 does not divide the channels: {len(up[T2])} up, {len(dn[T2])} down")
    for m in (hi2, lo2):
        v = verdict[T2][m]
        if not (v["moved"] or v["moved_either_way"]):
            bad.append(f"T2's {m} ({v['delta']:+.4f}) does not separate from its matched null, so the two "
                       f"extremes this figure names are not movements the paper can call one")
    if up[T3]:
        bad.append(f"T3 raised {sorted(up[T3])}, so it does not lower every channel it moves")
    if bad:
        raise SystemExit("F8 refuses to draw: its title says the claim-withdrawing edit divides the channels "
                         "and the sentence-joining edit lowers every one it moves. Violations: "
                         + "; ".join(bad))

    # The left third is the row labels' column, reserved before anything is drawn. Three lines of text hung
    # off a tick sit outside the axes, so a default margin puts them outside the FIGURE, and the only report
    # of that is a tight bounding box wider than the page's column -- which LaTeX answers by shrinking every
    # point size declared above.
    fig, ax = plt.subplots(figsize=(WIDTH_IN - 0.08, 2.62))
    LEFT_FRAC, RIGHT_FRAC = 0.335, 0.995
    fig.subplots_adjust(left=LEFT_FRAC, right=RIGHT_FRAC, top=0.845, bottom=0.245)
    ax.axvline(0, color="#5b6770", lw=0.7, zorder=3)
    # Spaced wider than one row unit because the two channels the arm hangs on sit on the same row and have
    # to be labelled above it and below it: at unit spacing each label came to rest halfway to the next row,
    # where a reader has to decide by hue which row it belongs to.
    ys = {t: (len(ORDER) - 1 - i) * ROW_GAP for i, t in enumerate(ORDER)}
    ax.set_yticks([])
    ax.set_ylim(-0.85, (len(ORDER) - 1) * ROW_GAP + 0.80)
    # Set from the data, because nothing drawn so far is data: the dots go on after the scale settles, and an
    # axis left to autoscale on a rule at zero and three strings would fit the labels around a range that
    # excludes every channel it is labelling.
    vals = [v for d in D.values() for v in d.values()]
    span = max(vals) - min(vals)
    ax.set_xlim(min(vals) - 0.03 * span, max(vals) + 0.03 * span)

    # How far apart the rungs of the dodge sit, and how far a named label clears the row, are both a marker
    # diameter -- so both are derived from it rather than typed. Typed, they were 0.145 of a row against a
    # marker that needs 0.155, which drew two of T1's channels as one dot.
    fig.canvas.draw()
    box = ax.get_window_extent()
    dia = (MS + MEW) / 72 * fig.dpi                                  # marker diameter, in pixels
    step = dia * 1.2 / (box.height / (ax.get_ylim()[1] - ax.get_ylim()[0]))
    levels = (0.0, step, -step, 2 * step, -2 * step)
    # A whole diameter clear of the outermost rung, not four tenths of one. Four tenths cleared the dot's
    # centre and not the dot: the label's mask is opaque, so the top rung of the dodge was drawn with a bite
    # out of it, and a clipped marker reads as a smaller marker.
    lab_off = 2 * step + dia * 1.0 / (box.height / (ax.get_ylim()[1] - ax.get_ylim()[0]))

    # The three channels the argument names, labelled where they sit. Everything else is a dot: naming
    # twelve channels three times over is the appendix figure's job, and it needs a page for it.
    #
    # Centred over the dot rather than hung off one side of it. A label anchored to the left of the deepest
    # dot has to be paid for in scale, and the loop below pays: hung outward, the labels pushed the axis out
    # to -1.27 for data that reaches -0.72, which puts every dot in the right-hand third of a mostly empty
    # panel. Centred, each label costs half its width on each side and the panel keeps its data.
    # One above its row and one below, because the two the arm hangs on sit on the SAME row: side by side
    # they printed as `structure compliance -0.223calibration honesty +0.131`, which is one string a reader
    # cannot parse and two numbers they cannot attach.
    named = [("T2_concede", "calibration_honesty", +1),
             ("T2_concede", "structure_compliance", -1),
             ("T3_lengthen", "clarity", +1)]
    labels = []
    for t, m, side in named:
        v = D[t][m]
        # Masked with the paper colour, because a label centred on its dot is as wide as its own words and
        # the widest of them is centred at +0.131: it spans the rule at zero, which is drawn in the same grey
        # as the T2 label, and the rule ran up the stem of the `i` in `calibration` so the word printed as
        # `cal bration`. The mask cannot cover a dot -- the loop below asserts every marker clears the label
        # box by its own radius -- nor another label, which the same loop asserts.
        labels.append(ax.text(v, ys[t] + side * lab_off, f"{SHORT[m]} {sgn(v, 3)}", ha="center",
                              va="bottom" if side > 0 else "top",
                              bbox=dict(facecolor="white", edgecolor="none", pad=0.6),
                              fontsize=PT_ANN, color=COL[t], zorder=5))

    # The net and the split ride IN the row label, the way fig3 puts its value in a tick label: a number
    # placed in the axes has to dodge twelve dots per row, and any position that clears them on this corpus
    # is one re-reading away from not clearing them.
    # Left-aligned in their own column rather than hung off the ticks: a tick label is right-aligned against
    # the axis, so three lines of unequal length come out ragged on the edge a reader's eye runs down.
    x_lab = -(LEFT_FRAC - 0.012) / (RIGHT_FRAC - LEFT_FRAC)
    for t in ORDER:
        r = arms[t]["pooled"]
        # Spelled so the counts add to twelve from the label's own words: two of T3's channels are exactly
        # unchanged, and a row reading "10 down, none up" leaves a reader to work out where the other two
        # went.
        flat = len(SHORT) - len(up[t]) - len(dn[t])
        split = f"{len(dn[t])} of {len(SHORT)} channels down, {len(up[t]) or 'none'} up"
        ax.text(x_lab, ys[t], f"{NICE[t]}\ncomposite {sgn(r['median_exact'], 3)} z\n"
                + split + (f", {flat} unchanged" if flat else ""),
                transform=ax.get_yaxis_transform(), ha="left", va="center", multialignment="left",
                fontsize=PT_TICK, color=COL[t], linespacing=1.35)
    ax.set_xlabel("median Δ per channel (z), one scale for all three edits", fontsize=PT_LAB)
    fig.suptitle("a withdrawn claim divides the channels; joining sentences lowers every one it moves",
                 fontsize=PT_TITLE, fontweight="bold", x=0.0, ha="left", y=0.995)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)

    # Stated as a rule under the axis, the way F4 states the same convention, and for the same reason: a
    # two-swatch key can only be drawn in one hue and the convention runs across three, so a key in any one
    # of them describes the other two rows in the wrong colour. Under the axis it also cannot land on a dot,
    # which a box inside the panel can as soon as a channel moves further than it did.
    fig.text((LEFT_FRAC + RIGHT_FRAC) / 2, 0.012,
             "filled = a channel outside the edit's licence; open = a licensed channel",
             ha="center", va="bottom", fontsize=PT_ANN, color="#3d474e")

    # Room for the three named channels, measured rather than guessed: a label anchored at a dot is drawn
    # outside it, so the deepest dot's label is what leaves the axes, and its width depends on the face and
    # the number. Expanded until every label is inside, then asserted. Half a pixel at the figure's own
    # resolution is below the width of a stem at any size this is printed at.
    # What a label occupies on the page is its mask, not its glyphs: the white patch is what hides the rule at
    # zero, so it is also what could hide a dot, and every measurement below is taken from it.
    def mask_box(t):
        patch = t.get_bbox_patch()
        return patch.get_window_extent() if patch is not None else t.get_window_extent()

    for _ in range(12):
        fig.canvas.draw()
        over, px_per_data = 0.0, None
        box = ax.get_window_extent()
        for txt in labels:
            tb = mask_box(txt)
            over = max(over, box.x0 - tb.x0, tb.x1 - box.x1)
        px_per_data = box.width / (ax.get_xlim()[1] - ax.get_xlim()[0])
        if over <= 0.5:
            break
        x0, x1 = ax.get_xlim()
        grow = over / px_per_data * 1.25
        ax.set_xlim(x0 - grow, x1 + grow)
    else:
        raise SystemExit("F8: the named-channel labels will not fit inside the scale")

    # The dots go on after the scale has settled, because how close two channels are ON THE PAGE is a
    # property of the scale, and the scale is not known until the labels have been fitted.
    px_in = fig.dpi
    box = ax.get_window_extent()
    dia = (MS + MEW) / 72 * px_in                                   # marker diameter, in pixels
    sep = dia / (box.width / (ax.get_xlim()[1] - ax.get_xlim()[0]))  # and the same distance, in z
    at = {}
    for t in ORDER:
        offs = dodge(D[t], sep, levels)
        for m, v in D[t].items():
            y = ys[t] + offs[m]
            at[(t, m)] = (v, y)
            ax.plot([v], [y], marker="o", ms=MS, zorder=4,
                    markerfacecolor="white" if m in LEGIT[t] else COL[t],
                    markeredgecolor=COL[t], markeredgewidth=MEW)

    # Three ways this figure can print a false page, all measured rather than eyeballed: a label pushed off
    # the axes, a label lying on a dot, and one dot drawn on top of another. The last is the one that reads
    # as data, because the row beside it says twelve.
    fig.canvas.draw()
    pts = {k: ax.transData.transform(v) for k, v in at.items()}
    for t in ORDER:
        ms = list(D[t])
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                (ax_, ay), (bx, by) = pts[(t, a)], pts[(t, b)]
                if abs(ax_ - bx) < dia * 0.95 and abs(ay - by) < dia * 0.95:
                    raise SystemExit(f"F8: {a} and {b} overlap on {t}, so the row draws fewer dots than the "
                                     f"twelve channels its label counts")
    for i, txt in enumerate(labels):
        tb = mask_box(txt)
        for other in labels[i + 1:]:
            ob = mask_box(other)
            if tb.x1 > ob.x0 - 2 and ob.x1 > tb.x0 - 2 and tb.y1 > ob.y0 - 1 and ob.y1 > tb.y0 - 1:
                raise SystemExit(f"F8: the labels {txt.get_text()!r} and {other.get_text()!r} run into each "
                                 f"other, which prints as one string a reader cannot parse")
        # Cleared by the marker's own radius rather than by two pixels: the mask is opaque and drawn above the
        # dots, so a dot whose centre sits just outside the box is drawn with a bite taken out of it -- which
        # reads as a smaller dot, not as a defect.
        for k, (px, py) in pts.items():
            if tb.x0 - dia / 2 <= px <= tb.x1 + dia / 2 and tb.y0 - dia / 2 <= py <= tb.y1 + dia / 2:
                raise SystemExit(f"F8: the label {txt.get_text()!r} covers the {k[1]} dot on {k[0]}")

    # A figure wider than the column it is placed in fails silently: \includegraphics[width=\textwidth]
    # scales an oversized figure DOWN, so every point size declared above becomes a smaller number on the
    # page and the type is illegible for a reason nothing else reports.
    placed = fig.get_tightbbox(fig.canvas.get_renderer()).width + 0.04
    if placed > WIDTH_IN + 0.01:
        raise SystemExit(f"F8: tight width {placed:.3f}in exceeds the {WIDTH_IN}in text column, so LaTeX "
                         f"will scale the figure to {WIDTH_IN / placed:.3f} of drawn size and every declared "
                         f"point size is wrong. Shorten the title.")

    fig.savefig(f"{OUT}/F8.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F8.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F8.pdf and F8.png")
    print(f"placed width {placed:.3f}in of {WIDTH_IN}in available; scale "
          f"{ax.get_xlim()[0]:+.3f} to {ax.get_xlim()[1]:+.3f}")
    for t in ORDER:
        r = arms[t]["pooled"]
        hi = max(D[t], key=lambda m: D[t][m])
        lo = min(D[t], key=lambda m: D[t][m])
        print(f"  {t}: composite {r['median']:+.4f} z, {len(up[t])} channels up and {len(dn[t])} down; "
              f"deepest {lo} {D[t][lo]:+.3f}, highest {hi} {D[t][hi]:+.3f}")
    for m in (hi2, lo2):
        v = verdict[T2][m]
        print(f"  T2 {m}: {v['delta']:+.4f}, two-sided p {v['p_exact_two']:.2g} against its matched null")
    print("  the title's two claims: T2's extremes point opposite ways and each separates from its own null; "
          "T3 raised none of the twelve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

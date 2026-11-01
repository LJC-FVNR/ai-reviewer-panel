#!/usr/bin/env python3
"""F6: what the extractor removes, who gets charged for it, and whether it costs a score. Appendix A's figure.

File names in figs/ are creation order, not document order. This one sits in appendix A, ahead of every figure
already in the appendices, so the document numbers it there; audit_submission.py derives the numbering from the
markdown order and compares it against what LaTeX typesets, so the mismatch is checked rather than remembered.

The recommendation section opens on this measurement -- inspect the text the pipeline hands a reviewer before an
agent score informs a decision -- and until now it reached the reader as two tables and a paragraph. Three
claims are drawn.

(a) The cut, per paper. Every one of the forty-eight supplied texts loses all of its document's back matter, and
    two thirds of them still point the reviewer into it. Drawn per paper rather than as the medians the appendix
    tabulates, because the claim is about how many documents are affected and a median cannot say.

(b) Who is charged for it. The share of untouched reviews that charge the author for a property of the supplied
    text rather than of the paper, in each population. The claim is that the rate holds across both corpora and
    both rosters, so the four bars are the claim and the pooled rate is the line behind them.

(c) Whether it costs a score, which is the part that does not resolve. Each population's within-paper paired gap
    with its 95 per cent interval, against zero and against its own roster's re-run band. One interval clears
    zero, the two readings of the same sixteen papers disagree in sign, and every median is inside the band it
    is drawn against: a null needs its intervals on the page, not a sentence saying it did not replicate.

Every value comes from extract_corpus.json, extract_charge_corpus.json, extract_cost.json, pooled_analysis.json
and n2_analysis.json, which the bundle ships. Nothing here is recomputed from reviews or documents.

The declined submissions are third-party work and are keyed by the arm-blind labels their corpus file carries.
No identifier of one reaches this figure, which draws them as an unlabelled row of points and a population name.

Drawn at final placed size (5.5in = NeurIPS text width).
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import rng, sgn  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

AN = "/path/to/workspace/ai_native_academia"
OUT = f"{AN}/figs"

PT_TITLE, PT_LAB, PT_TICK, PT_ANN = 8.0, 7.5, 7.0, 6.4
FONT = "Arimo"
C_EIGHT, C_FIVE = "#08519c", "#d94801"
INK, MUTE, BAND = "#14181c", "#3d474e", "#dfe6ec"
# The four populations under the names appendix A's tables give them, the roster each was read on, and the
# order they are drawn in: the two readings of the accepted sixteen at the ends, so that the sign disagreement
# between them in panel (c) is the first thing a reader's eye crosses.
POPS = [("accepted 16, five slots, untouched", "accepted 16, five slots", "five"),
        ("declined 32, five slots, untouched", "rejected 32, five slots", "five"),
        ("accepted 16, eight slots, untouched", "accepted 16, eight slots", "eight")]
CHARGE = "charge an extract-only property"

plt.rcParams.update({
    "font.family": FONT, "font.size": PT_TICK,
    "mathtext.fontset": "custom", "mathtext.rm": FONT, "mathtext.sf": FONT,
    "mathtext.it": f"{FONT}:italic", "mathtext.bf": f"{FONT}:bold",
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "pdf.fonttype": 42,
})


def main():
    os.makedirs(OUT, exist_ok=True)
    docs = json.load(open(f"{AN}/extract_corpus.json"))["documents"]
    charge = json.load(open(f"{AN}/extract_charge_corpus.json"))["populations"]
    cost = json.load(open(f"{AN}/extract_cost.json"))
    band = {"five": json.load(open(f"{AN}/pooled_analysis.json"))["band_rerun_preregistered"],
            "eight": json.load(open(f"{AN}/n2_pia_cursor8/n2_analysis.json"))["rerun_band_this_roster"]}

    fig = plt.figure(figsize=(5.5, 3.55))
    # One gridspec per row, because the rows' left margins differ and a margin is a fraction of the canvas:
    # matplotlib reserves no room for a tick label, so the margin has to hold the widest label of its own row
    # inside the figure box. The bottom row's population names are three times the width of "declined 32".
    gs_t = fig.add_gridspec(1, 1, left=0.148, right=0.988, top=0.925, bottom=0.700)
    gs_b = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.12],
                            left=0.238, right=0.988, top=0.545, bottom=0.135, wspace=0.10)
    axA = fig.add_subplot(gs_t[0, 0])
    axB, axC = fig.add_subplot(gs_b[0, 0]), fig.add_subplot(gs_b[0, 1])

    # ---- (a) the cut, per paper ------------------------------------------------------------------------
    rows = list(docs)                      # "accepted 16, preprint text", "declined 32, as-submitted PDF"
    short = [r.split(",")[0].replace("declined", "rejected") for r in rows]
    ptsA, n_ptr, n_back = [], 0, 0
    for i, r in enumerate(rows):
        papers = docs[r]
        for v in papers.values():
            pointing = v["appendix_pointers"] > 0
            n_ptr += pointing
            n_back += v["reviewer_words"] != v["reviewer_body_words"]
            ptsA.append((v["body_share"], i))
            axA.scatter([v["body_share"]], [i], s=15, zorder=3,
                        marker="o", c=(INK if pointing else "none"),
                        edgecolors=("white" if pointing else MUTE), linewidths=(0.5 if pointing else 0.8))
        med = st.median(v["body_share"] for v in papers.values())
        axA.plot([med, med], [i - 0.30, i + 0.30], color=C_FIVE, lw=1.1, zorder=4)
        axA.text(med, i - 0.38, sgn(med, 3, plus=False), ha="center", va="bottom",
                 fontsize=PT_ANN, color=C_FIVE, zorder=4)
    # The whole point of drawing this per paper: no supplied text carries any back matter, whatever share of
    # the body it carries, and two thirds of them point into the part that is gone. Both halves are asserted
    # so that a re-extraction changing either stops the build instead of leaving the annotation to say it.
    total = sum(len(docs[r]) for r in rows)
    assert n_back == 0, f"{n_back} supplied texts carry back matter; the annotation says none do"
    assert 0 < n_ptr < total, (n_ptr, total)
    axA.set_yticks(range(len(rows)))
    axA.set_yticklabels(short, fontsize=PT_ANN)
    axA.set_ylim(len(rows) - 0.30, -1.35)
    axA.set_xlabel("share of the document's body supplied to the reviewer", fontsize=PT_LAB)
    axA.set_title("a  no supplied text carries the back matter it points at", fontsize=PT_TITLE,
                  fontweight="bold", loc="left", pad=5)
    axA.tick_params(labelsize=PT_TICK)
    axA.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axA.spines[s].set_visible(False)
    axA.grid(axis="y", color="#eef1f4", lw=0.6, zorder=0)
    legA = axA.legend(handles=[Line2D([], [], marker="o", ls="none", ms=3.4, mfc=INK, mec="white",
                                      label=f"points into missing back matter: {n_ptr} of {total}"),
                              Line2D([], [], marker="o", ls="none", ms=3.6, mfc="none", mec=MUTE, mew=0.8,
                                     label=f"does not: {total - n_ptr} of {total}")],
                      loc="upper left", bbox_to_anchor=(-0.005, 1.06), frameon=False, fontsize=PT_ANN,
                      handlelength=1.0, labelspacing=0.28, borderpad=0.0, handletextpad=0.4, ncol=2,
                      columnspacing=1.1)

    # ---- (b) who is charged for it ---------------------------------------------------------------------
    ypos = {key: i for i, (key, _, _) in enumerate(POPS)}
    rate, nchg, nrev = {}, {}, {}
    for key, lab, roster in POPS:
        c = charge[key]
        nchg[key] = c["by_charge"][CHARGE]["reviews"]
        nrev[key] = c["reviews"]
        rate[key] = nchg[key] / nrev[key]
        axB.barh([ypos[key]], [rate[key]], height=0.52, zorder=3,
                 color=(C_EIGHT if roster == "eight" else C_FIVE), linewidth=0)
        # Each count sits outside its bar and two of the four bars end left of the pooled line, so the label
        # carries its own paper-coloured patch: an unboxed label has the dashed rule running between its
        # digits, and a rule through a numeral is a misread number.
        axB.text(rate[key] + 0.006, ypos[key], f"{nchg[key]} of {nrev[key]}", ha="left", va="center",
                 fontsize=PT_ANN, color=INK, zorder=4,
                 bbox=dict(facecolor="white", edgecolor="none", pad=0.8))
    pooled = sum(nchg.values()) / sum(nrev.values())
    # Both reference lines stop short of the strip the annotations occupy. Drawn across the full axes, each
    # one struck through the label that explains it, and a rule through a numeral is a misread digit.
    axB.plot([pooled, pooled], [len(POPS) - 0.45, -0.52], color=MUTE, lw=0.7, ls=(0, (3.0, 2.0)),
             zorder=2, clip_on=False)
    axB.set_yticks(range(len(POPS)))
    axB.set_yticklabels([lab for _, lab, _ in POPS], fontsize=PT_ANN)
    axB.set_ylim(len(POPS) - 0.45, -1.30)
    axB.set_xlim(0, max(rate.values()) * 1.42)
    axB.set_xlabel("share of reviews charging the extract", fontsize=PT_LAB)
    axB.set_title("b  one review in four or five", fontsize=PT_TITLE, fontweight="bold", loc="left", pad=5)
    # The title reads the dashed line, so it is bounded by it rather than by the widest bar.
    assert 0.20 < pooled < 0.25, pooled
    axB.tick_params(labelsize=PT_TICK)
    axB.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)
    axB.text(pooled, -0.62, f"pooled {sgn(pooled, 3, plus=False)}\nover {sum(nrev.values()):,} reviews",
             ha="center", va="bottom", fontsize=PT_ANN, color=MUTE, linespacing=1.3, zorder=4)

    # ---- (c) whether it costs a score ------------------------------------------------------------------
    ptsC, clears, counts = [], [], []
    for key, lab, roster in POPS:
        c = cost[key]
        lo, hi = c["paired_ci"]
        b = band[roster]
        # The band belongs to the roster the population was read on, so it is drawn across that row alone. One
        # band across all four rows would compare three five-slot readings against the eight-slot roster's
        # noise, which is the error appendix H exists to rule out.
        axC.add_patch(plt.Rectangle((-b, ypos[key] - 0.34), 2 * b, 0.68, facecolor=BAND, lw=0, zorder=0))
        axC.plot([lo, hi], [ypos[key]] * 2, color=MUTE, lw=0.9, zorder=3, solid_capstyle="butt")
        axC.scatter([c["paired_gap_median"]], [ypos[key]], s=17, zorder=4,
                    c=(C_EIGHT if roster == "eight" else C_FIVE), linewidths=0.5, edgecolors="white")
        ptsC += [(lo, ypos[key]), (hi, ypos[key]), (c["paired_gap_median"], ypos[key])]
        clears.append((lab, not (lo <= 0 <= hi)))
        counts.append((ypos[key], f"{c['paired_positive']} of {c['papers_with_both']} up"))
    axC.plot([0, 0], [len(POPS) - 0.45, -0.52], color="#8c99a4", lw=0.7, zorder=1, clip_on=False)
    axC.set_yticks(range(len(POPS)))
    axC.set_yticklabels([])
    # The right limit is set by the widest count label, not by the widest interval: the labels sit in data
    # coordinates, so the room they need is bought in data units. An explicit limit also keeps the zero line
    # and the shaded bands in the same place if a rescore moves an end.
    lo_lim = min(cost[k]["paired_ci"][0] for k, _, _ in POPS) - 0.045
    hi_lim = max(cost[k]["paired_ci"][1] for k, _, _ in POPS) + 0.185
    axC.set_xlim(lo_lim, hi_lim)
    # The counts are a right-hand column rather than a label at each interval's end. Set beside the ends they
    # fall on top of the shaded band on the two rows whose interval is short, and a label over a band is either
    # a white hole in it or a rule through the digits.
    for y, txt in counts:
        axC.text(hi_lim - 0.004, y, txt, ha="right", va="center", fontsize=PT_ANN, color=INK, zorder=4)
    axC.set_ylim(len(POPS) - 0.45, -1.30)
    axC.set_xlabel("paired gap, charging minus not (z)", fontsize=PT_LAB)
    axC.set_title("c  no score cost survives replication", fontsize=PT_TITLE, fontweight="bold",
                  loc="left", pad=5)
    axC.tick_params(labelsize=PT_TICK)
    axC.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axC.spines[s].set_visible(False)
    # The two readings of the same sixteen papers, which is where the null is decided.
    acc5 = cost["accepted 16, five slots, untouched"]["paired_gap_median"]
    acc8 = cost["accepted 16, eight slots, untouched"]["paired_gap_median"]
    assert acc5 * acc8 < 0, ("the two readings of the accepted sixteen no longer disagree in sign", acc5, acc8)
    assert sum(1 for _, c in clears if c) == 1, clears
    widest = max(abs(cost[k]["paired_gap_median"]) for k, _, _ in POPS)
    assert widest < band["five"], (widest, band["five"])
    axC.text(0.0, -0.62,
             f"shaded: each roster's own re-run band\nthe same sixteen papers give "
             f"{sgn(acc5, 3)} and {sgn(acc8, 3)}",
             transform=axC.get_yaxis_transform(), ha="left", va="bottom", fontsize=PT_ANN,
             color=INK, linespacing=1.3, zorder=5)

    # Two panels carry a key or an annotation over their own data area, so what would otherwise be an eye
    # check is a measurement: no drawn point may fall inside one. A key that hides a point removes exactly
    # the observation it claims to identify.
    fig.canvas.draw()
    rnd = fig.canvas.get_renderer()
    bb = legA.get_window_extent(rnd)
    hidden = [pt for pt in ptsA if bb.contains(*axA.transData.transform(pt))]
    assert not hidden, f"panel (a): legend covers {hidden}"

    # The bottom row's two axis labels are the tightest fit on the canvas. Each is centred under its own axes
    # and long enough to reach past it, so a label that grows by a word runs into its neighbour and the pair
    # reads as one line of prose. Measured against the gap rather than looked at.
    # Panel (c)'s counts are a column, so what has to hold is that the column starts right of every interval
    # end: a count set over its own row's error bar reads as a point on it.
    for t in axC.texts:
        e = t.get_window_extent(rnd)
        x0 = axC.transData.inverted().transform((e.x0, e.y0))[0]
        if t.get_ha() == "right":
            assert x0 > max(cost[k]["paired_ci"][1] for k, _, _ in POPS) + 0.01, (t.get_text(), x0)

    lbB, lbC = axB.xaxis.label.get_window_extent(rnd), axC.xaxis.label.get_window_extent(rnd)
    gap_in = (lbC.x0 - lbB.x1) / fig.dpi
    assert gap_in > 0.06, f"the bottom row's axis labels are {gap_in:.3f} in apart"
    assert lbB.x0 > 0 and lbC.x1 < fig.get_window_extent().x1, "an axis label runs off the canvas"

    fig.savefig(f"{OUT}/F6.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F6.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F6.pdf and F6.png")

    # ---- what the panels assert, printed so the caption can be checked against them ---------------------
    print(f"(a) {total} papers, {n_ptr} pointing into missing back matter, {n_back} carrying any; "
          f"median body share " + ", ".join(f"{s} {st.median(v['body_share'] for v in docs[r].values()):.3f}"
                                            for r, s in zip(rows, short)))
    print(f"(b) pooled {sum(nchg.values())} of {sum(nrev.values())} = {pooled:.4f}; per population "
          + "; ".join(f"{lab} {nchg[k]}/{nrev[k]} = {rate[k]:.4f}" for k, lab, _ in POPS))
    for key, lab, roster in POPS:
        c = cost[key]
        print(f"(c) {lab:<28} median {c['paired_gap_median']:+.4f} CI "
              f"{rng(*c['paired_ci'], 3)} clears zero: {not (c['paired_ci'][0] <= 0 <= c['paired_ci'][1])}; "
              f"{c['paired_positive']} of {c['papers_with_both']} up; band {band[roster]:.4f}")
    print(f"(c) the accepted sixteen read twice: {sgn(acc5, 3)} and {sgn(acc8, 3)}, opposite signs; "
          f"widest median {widest:.4f} inside the five-model band {band['five']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

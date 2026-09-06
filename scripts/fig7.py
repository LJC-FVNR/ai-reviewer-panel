#!/usr/bin/env python3
"""F7: the title claim, drawn. No bar on the grade axis admits a published paper; the ordering the same
reviewers produce is nearly the same one. Appendix C's figure.

File names in figs/ are creation order, not document order. This one sits at the end of the appendix section on
the variance ladder, ahead of the transform figures, so the document numbers it there; audit_submission.py
derives the numbering from the markdown order and compares it against what LaTeX typesets.

Both claims reached the reader as a table and a clause. They are the two halves of the paper's own title, and a
reader who looks only at the figures has so far seen the grade distribution and the ranking but neither the
consensus ladder nor the agreement structure behind the aggregation null.

(a) The grade axis, asked for a decision rule. Four bars a venue might set, from the strictest to the one nearly
    every reading clears, against the share of readings that clear each. The bar is the panels; the two markers
    are the papers, once counting a paper that clears in either of its two panels and once requiring both. Where
    those markers separate, a paper clears the bar in one reading of unchanged text and fails it in the other.

(b) The same five reviewers, asked for an ordering. Every pair of slots on each population, as pairwise rank
    agreement on the composite, with the median of the ten pairs marked. High agreement is why averaging the
    five cannot repair what §4 measures, and the fall on the accepted set is where the population narrows to
    what a committee faces.

Every value comes from consensus_bars.json and reliability.json, which the bundle ships. Nothing here is
recomputed from reviews.

Drawn at final placed size (5.5in = NeurIPS text width).
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
from matplotlib.lines import Line2D

AN = "/path/to/workspace/ai_native_academia"
OUT = f"{AN}/figs"

PT_TITLE, PT_LAB, PT_TICK, PT_ANN = 8.0, 7.5, 7.0, 6.4
FONT = "Arimo"
C_FIVE = "#d94801"
INK, MUTE, PALE = "#14181c", "#3d474e", "#c8d2dc"

# The rungs under the names §3's table gives them, wrapped to the two lines a full-width row can hold, in the
# table's own order: strictest first, so the bars grow downward and the one bar most papers clear is last.
RUNGS = {"every reviewer at Minor Revision or better": "every reviewer at\nMinor Revision or better",
         "any single reviewer says Accept": "any single reviewer\nsays Accept",
         "modal grade at Minor Revision or better": "modal grade at\nMinor Revision or better",
         "every reviewer at Major Revision or better": "every reviewer at\nMajor Revision or better"}
# The populations of the variance ladder, ordered by proximity to the set a programme committee decides over,
# under the keys reliability.json carries and the names the appendix's ladder table gives them.
POPS = [("ICLR rejected, all 32 (heterogeneous)", "declined 32, all"),
        (".. low-rated 16 only", "declined 16, lower-rated"),
        (".. high-rated 16 only", "declined 16, higher-rated"),
        ("ICLR accepted 16 (homogeneous)", "accepted 16")]

plt.rcParams.update({
    "font.family": FONT, "font.size": PT_TICK,
    "mathtext.fontset": "custom", "mathtext.rm": FONT, "mathtext.sf": FONT,
    "mathtext.it": f"{FONT}:italic", "mathtext.bf": f"{FONT}:bold",
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "pdf.fonttype": 42,
})


def main():
    os.makedirs(OUT, exist_ok=True)
    lad = json.load(open(f"{AN}/consensus_bars.json"))
    rel = json.load(open(f"{AN}/reliability.json"))["composite"]

    fig = plt.figure(figsize=(5.5, 3.50))
    # One gridspec per row: both rows carry two-line names in the left margin and the margin is a fraction of
    # the canvas, so each row reserves the width of its own widest name rather than of the figure's.
    gs_t = fig.add_gridspec(1, 1, left=0.258, right=0.988, top=0.935, bottom=0.618)
    gs_b = fig.add_gridspec(1, 1, left=0.258, right=0.988, top=0.462, bottom=0.135)
    axA, axB = fig.add_subplot(gs_t[0, 0]), fig.add_subplot(gs_b[0, 0])

    # ---- (a) the grade axis, asked for a decision rule -------------------------------------------------
    bars = {b["bar"]: b for b in lad["bars"]}
    assert sorted(bars) == sorted(RUNGS), f"the ladder's rungs read {sorted(bars)}"
    n_pan, n_pap = lad["n_panels"], lad["n_papers"]
    ptsA, labA = [], []
    for i, key in enumerate(RUNGS):
        b = bars[key]
        share = b["panels"] / n_pan
        axA.barh([i], [share], height=0.46, color=C_FIVE, zorder=3, linewidth=0)
        for count, filled in ((b["papers_any"], False), (b["papers_both"], True)):
            x = count / n_pap
            axA.scatter([x], [i], s=17, zorder=4, marker="o",
                        c=(INK if filled else "none"), edgecolors=("white" if filled else MUTE),
                        linewidths=(0.5 if filled else 0.8))
            ptsA.append((x, i))
        # The count is the claim on this row, so it is spelled out rather than left to the axis, and where a
        # paper clears the bar in one reading and not in the other the two counts are named in the same breath.
        what = f"{b['panels']} of {n_pan} panels"
        if b["papers_any"] != b["papers_both"]:
            # A row where the two markers separate is the instability the section reports, and it is the one
            # thing a marker pair cannot say on its own, so those rows carry it as a clause. The rows where the
            # markers coincide keep the short label: a long one there would reach past the canvas.
            once = "1 paper clears" if b["papers_any"] == 1 else f"{b['papers_any']} papers clear"
            what += f" \u2014 {once} it once, {b['papers_both'] or 'none'} twice"
        t = axA.text(max(share, b["papers_any"] / n_pap) + 0.014, i, what,
                     ha="left", va="center", fontsize=PT_ANN, color=INK, zorder=5)
        labA.append(t)
    # What the panel is drawn to show: the strictest bar is cleared by nothing, the loosest by most papers in
    # both readings, and in between a bar is cleared by more papers once than twice. Asserted so that a rescore
    # changing any of the three stops the build rather than leaving the titles to say it.
    strict, loose = bars["every reviewer at Minor Revision or better"], bars[list(RUNGS)[-1]]
    assert strict["panels"] == 0, strict
    assert loose["papers_both"] == loose["papers_any"] > n_pap / 2, loose
    flip = [b for b in lad["bars"] if b["papers_any"] > b["papers_both"]]
    assert flip, "no rung is cleared by more papers in one panel than in both"
    axA.set_yticks(range(len(RUNGS)))
    axA.set_yticklabels(list(RUNGS.values()), fontsize=PT_ANN, linespacing=1.25)
    axA.set_ylim(len(RUNGS) - 0.42, -1.02)
    # A rung cleared by nothing is drawn as a marker pair at zero, so the limit starts left of it: on the
    # spine the pair is half a mark wide and the row reads as though nothing were plotted on it at all.
    axA.set_xlim(-0.014, 1.0)
    axA.set_xticks([i / 5 for i in range(6)])
    axA.set_xlabel("share of readings of the published papers that clear the bar", fontsize=PT_LAB)
    axA.set_title("a  the only bar most published papers clear is the loosest", fontsize=PT_TITLE,
                  fontweight="bold", loc="left", pad=5)
    axA.tick_params(labelsize=PT_TICK)
    axA.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axA.spines[s].set_visible(False)
    axA.grid(axis="y", color="#eef1f4", lw=0.6, zorder=0)
    legA = axA.legend(handles=[plt.Rectangle((0, 0), 1, 1, fc=C_FIVE, ec="none",
                                            label=f"panels, of {n_pan}"),
                              Line2D([], [], marker="o", ls="none", ms=3.6, mfc="none", mec=MUTE, mew=0.8,
                                     label=f"papers clearing in one panel, of {n_pap}"),
                              Line2D([], [], marker="o", ls="none", ms=3.4, mfc=INK, mec="white",
                                     label="papers clearing in both")],
                      loc="upper right", bbox_to_anchor=(1.004, 1.0), frameon=False, fontsize=PT_ANN,
                      handlelength=1.0, labelspacing=0.28, borderpad=0.0, handletextpad=0.4, ncol=3,
                      columnspacing=1.0)

    # ---- (b) the same reviewers, asked for an ordering ------------------------------------------------
    meds, ptsB = [], []
    for i, (key, _) in enumerate(POPS):
        d = rel[key]
        pairs = list(d["inter_slot_pairs"].values())
        assert len(pairs) == 10, (key, len(pairs))
        axB.scatter(pairs, [i] * len(pairs), s=13, zorder=3, marker="o",
                    c="none", edgecolors=MUTE, linewidths=0.7)
        med = d["inter_slot_median"]
        axB.plot([med, med], [i - 0.28, i + 0.28], color=C_FIVE, lw=1.2, zorder=4)
        axB.text(med, i - 0.36, sgn(med, 3), ha="center", va="bottom", fontsize=PT_ANN, color=C_FIVE, zorder=5)
        meds.append(med)
        ptsB += [(p, i) for p in pairs]
    # The fall is the claim, and it is a fall onto the population a committee decides over rather than noise
    # among the three wider ones: the accepted set's median sits below every pair-median above it.
    assert max(meds[:3]) - meds[-1] > 0.15, meds
    assert meds[-1] < min(meds[:3]), meds
    axB.set_yticks(range(len(POPS)))
    axB.set_yticklabels([lab for _, lab in POPS], fontsize=PT_ANN)
    axB.set_ylim(len(POPS) - 0.42, -1.02)
    lo = min(p for p, _ in ptsB)
    axB.set_xlim(lo - 0.045, 1.0)
    axB.set_xlabel("agreement between two reviewer slots (Spearman)", fontsize=PT_LAB)
    axB.set_title("b  yet the five reviewers order papers alike, least on the narrowest set",
                  fontsize=PT_TITLE, fontweight="bold", loc="left", pad=5)
    axB.tick_params(labelsize=PT_TICK)
    axB.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)
    axB.grid(axis="y", color="#eef1f4", lw=0.6, zorder=0)
    legB = axB.legend(handles=[Line2D([], [], marker="o", ls="none", ms=3.4, mfc="none", mec=MUTE, mew=0.7,
                                     label="one of the ten slot pairs"),
                               Line2D([], [], color=C_FIVE, lw=1.2, label="median pair")],
                      loc="upper left", bbox_to_anchor=(-0.004, 1.0), frameon=False, fontsize=PT_ANN,
                      handlelength=1.0, labelspacing=0.28, borderpad=0.0, handletextpad=0.4, ncol=2,
                      columnspacing=1.0)

    # Both panels carry a key over their own data area and (a) a count label beside every bar, so what would
    # otherwise be an eye check is a measurement: no drawn mark may fall under a key, and no count label may
    # run off the canvas or into the key above it.
    fig.canvas.draw()
    rnd = fig.canvas.get_renderer()
    for ax, leg, pts in ((axA, legA, ptsA), (axB, legB, ptsB)):
        bb = leg.get_window_extent(rnd)
        hidden = [pt for pt in pts if bb.contains(*ax.transData.transform(pt))]
        assert not hidden, f"a key covers {hidden}"
    right = fig.get_window_extent().x1
    for t in labA:
        e = t.get_window_extent(rnd)
        assert e.x1 < right, f"the count label {t.get_text()!r} runs off the canvas"
        assert not legA.get_window_extent(rnd).overlaps(e), f"the key covers {t.get_text()!r}"
    # A key drawn level with its own title reads as part of the title, and (b)'s medians are labelled in the
    # strip between two rows, where the row above draws its pairs. Both are measured rather than looked at.
    for ax, leg in ((axA, legA), (axB, legB)):
        assert not leg.get_window_extent(rnd).overlaps(ax.title.get_window_extent(rnd)), "a key sits in a title"
    for t in axB.texts:
        e = t.get_window_extent(rnd)
        near = [pt for pt in ptsB if e.contains(*axB.transData.transform(pt))]
        assert not near, f"the median label {t.get_text()!r} covers {near}"
    # (a)'s axis label sits directly above (b)'s title, and set at the two sizes they are the pair reads as one
    # block of text unless the row boundary leaves room: the same clearance the appendix's other two-row figure
    # holds, measured rather than eyed, because the room is bought in the gridspec and not by the label.
    gap_in = (axA.xaxis.label.get_window_extent(rnd).y0 - axB.title.get_window_extent(rnd).y1) / fig.dpi
    assert gap_in > 0.12, f"panel (a)'s axis label is {gap_in:.3f} in above panel (b)'s title"

    fig.savefig(f"{OUT}/F7.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F7.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F7.pdf and F7.png")

    # ---- what the panels assert, printed so the caption can be checked against them ---------------------
    for key in RUNGS:
        b = bars[key]
        print(f"(a) {key:<44} {b['panels']:>2} of {n_pan} panels; papers {b['papers_any']:>2} in one panel, "
              f"{b['papers_both']:>2} in both, of {n_pap}")
    print(f"(a) the strictest bar is cleared by no panel; the loosest by {loose['papers_both']} of {n_pap} "
          f"papers in both readings; rungs where one panel is not both: {len(flip)}")
    for (key, lab), med in zip(POPS, meds):
        d = rel[key]
        print(f"(b) {lab:<26} median {sgn(med, 4)} over ten pairs, range "
              f"{sgn(d['inter_slot_min'], 4)} to {sgn(d['inter_slot_max'], 4)}")
    print(f"(b) flat across the three declined populations at {', '.join(sgn(m, 3) for m in meds[:3])}, "
          f"then {sgn(meds[-1], 3)} on the accepted sixteen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

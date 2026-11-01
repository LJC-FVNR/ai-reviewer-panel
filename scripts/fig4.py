#!/usr/bin/env python3
"""F4: which channels the two presentation edits moved, and which they had no business moving.

A composite that drops tells you the panel noticed. It does not tell you the panel was WRONG. That
distinction is what this figure carries, and it is the difference between "agent reviewers respond to
writing quality" (unremarkable, arguably correct) and "presentation contaminates content judgement"
(the paper's claim).

Each transform gets a set of channels it may legitimately move:

  T1  figure/table blocks relocated to end matter -> structure_compliance, clarity, figure_quality
  T3  adjacent sentences joined                   -> clarity, structure_compliance, figure_quality

T3 is charged for figure_quality because audit_t3_captions.py shows it rewrote 320 of the 1183 caption
lines (27%) in 46 of the 47 papers it reached -- captions contain adjacent short sentences like any other
text -- so caption readability really did change. Claiming figure_quality as a clean leak was an
overclaim, caught by reading the variant texts rather than the numbers. T1 keeps figure_quality as
legitimate on different grounds: it rewrites no caption line at all (same audit) but separates every
figure from the sentence that refers to it, which degrades how well the figure serves a reader.

Run audit_t3_captions.py before changing either LEGIT set. Two earlier counts did not reproduce. One was a
hand diff with a regex for anything beginning "Figure" or "Table", which matched running-text references and
missed caption continuation lines: "11 caption lines across 5 of 8 papers", off by roughly 5x. The other was
this script's own audit comparing a baseline multiset against a variant SET, so a caption line the extractor
emits twice in both texts was charged once as changed; it gave T1 three lines in two papers, and all three
were duplicate lines present in both texts.

Everything else is a channel neither edit can justify moving: a permutation of existing blocks, or a
join of two adjacent sentences, does not alter what was proved, what is new, whether the baselines were
adequate, or whether a reader could reproduce the work.

The claim is about those nine channels AS A GROUP, so the group is what each panel header states, read
from pia_null.json: the median over papers of the mean z across the nine, against a matched
randomisation null, with the weaker of that test's two p-values. The bars stay per channel because they
are the diagnostic -- they say which channels carry the group's movement -- but they no longer carry a
count. The title carries no count of channels past a threshold, because no such threshold appears anywhere
else in the paper and no measurement produces one: the same quantity comes out
8/9, 5/3, 3/2 or 2/1 under four defensible definitions. The group has no such knob. Its only free choice
is LEGIT above, which is fixed by argument before any scoring, and nine channels carry roughly a third
of one channel's noise, which is why the group clears a matched null that most single channels cannot.

The two arms answer differently, and that is the figure. Joining sentences moves the nine channels it
cannot justify, at -0.109 z with three of them surviving multiplicity control. Relocating figures does
not: its nine sit at -0.006 z with a p near a half, and not one of them survives in either direction,
while the channels it does move are ones it is licensed to move. An instrument that responds to what an
edit legitimately touched and stays quiet elsewhere is behaving correctly, which is what makes the other
arm's behaviour a defect rather than noise.

Note the claim is about CONTENT, not text. T3 did rewrite sentences inside the related-work section, so
it touched that text; what it cannot have changed is which prior work is cited or how it is
characterised. The title is worded to say the channel could not be justified, not that the edit never
reached those pages.

Drawn as two signed panels on ONE shared scale, so a bar in the left panel and a bar in the right are
the same length for the same z. It used to be a single mirrored panel plotting magnitude outward, which
requires every median to be negative; five of T1's twelve are positive on this corpus, and mirrored
magnitudes would have drawn each of them as a loss. Signs are drawn, not assumed, and the shared scale
is asserted at run time.

Reads pooled_analysis.json for the channel medians and pia_null.json for the groups, both on the
five-slot roster over all forty-eight papers, day-matched. Drawn at final placed size.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import pfmt, sgn  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

WS = "/path/to/workspace"
AN = f"{WS}/ai_native_academia"
OUT = f"{AN}/figs"
NULL = f"{AN}/pia_null.json"
ROSTER = "5model_pooled"   # the roster and reading whose per-channel medians this figure draws

LEFT, RIGHT = "T1_endmatter", "T3_lengthen"
NICE = {LEFT: "T1  figures to end matter", RIGHT: "T3  join sentences"}
LEGIT = {LEFT: {"structure_compliance", "clarity", "figure_quality"},
         RIGHT: {"clarity", "structure_compliance", "figure_quality"}}
SHORT = {"significance": "significance", "novelty": "novelty", "rigor": "rigor",
         "statistical_soundness": "statistical soundness", "calibration_honesty": "calibration honesty",
         "clarity": "clarity", "structure_compliance": "structure compliance",
         "reproducibility": "reproducibility", "related_work": "related work",
         "figure_quality": "figure quality", "breadth_generality": "breadth / generality",
         "overall_recommendation": "overall recommendation"}
WIDTH_IN = 5.5          # NeurIPS \textwidth, and the size everything here is drawn at
C_LEGIT, C_LEAK = "#8fb4d9", "#08519c"
C_LEGIT_R, C_LEAK_R = "#9ecb9e", "#3f7f3f"
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


def group(pn, t, draws):
    """The non-allotted group's delta and the weaker of its two p-values, for transform t.

    Both nulls must clear 0.05 for pia_null.py to call a group moved, so the p worth printing is the
    larger of them -- and the assignment count that goes with it belongs to whichever null that was,
    since the two are drawn against different numbers of assignments and only the winner's floor is a
    true bound on the printed value.
    """
    ax = next(a for a in pn[t]["axes"] if a["allotted"] is False and a["n_channels"] > 1)
    if ax["exact_assignments"] is None:
        raise SystemExit(f"F4: {t}'s group axis carries no enumerated null; its p cannot be drawn")
    p, n = ((ax["p_exact"], ax["exact_assignments"]) if ax["p_exact"] >= ax["p_pooled"]
            else (ax["p_pooled"], draws))
    return dict(delta=ax["delta"], n=ax["n_channels"], p=p, moved=ax["moved"],
                text=pfmt(p, n, places=2, rel=True))


def main():
    if not os.path.exists(NULL):
        raise SystemExit(f"F4: {NULL} missing -- run pia_null.py first")
    os.makedirs(OUT, exist_ok=True)
    J = json.load(open(NULL))
    R = J["rosters"]
    if ROSTER not in R:
        raise SystemExit(f"F4: no {ROSTER} roster in pia_null.json; have {list(R)}")
    pn = R[ROSTER]["transforms"]
    for t in (LEFT, RIGHT):
        if t not in pn:
            raise SystemExit(f"F4: {t} not in pia_null.json[{ROSTER}]; have {list(pn)}")
    # One channel per single-channel axis, which is where the per-channel median lives. Taking it from
    # the same file as the group means the bars and the header they decompose cannot disagree.
    D = {t: {a["axis"]: a["delta"] for a in pn[t]["axes"] if a["n_channels"] == 1} for t in (LEFT, RIGHT)}
    G = {t: group(pn, t, J["draws"]) for t in (LEFT, RIGHT)}
    unknown = sorted({m for d in D.values() for m in d} - set(SHORT))
    if unknown:
        raise SystemExit(f"F4: no short label for {unknown}; the panel would print a raw metric key")

    # The title is a claim about the two arms answering differently, so it is settled before anything is
    # drawn. Three conjuncts, each of them the section's: the left arm's nine do not separate from their
    # null, none of them survives multiplicity control in either direction, and the right arm's nine do
    # separate. A figure that keeps its title after the data stops supporting it is the worst artifact
    # here, because it is the one a reader trusts without checking.
    bad = []
    if G[LEFT]["moved"]:
        bad.append(f"{LEFT}'s nine moved: {G[LEFT]['delta']:+.4f} p {G[LEFT]['p']:.4f}")
    stray = [m for m in pn[LEFT]["leaks_bh_q05"] + pn[LEFT]["leaks_bh_q05_two_sided"]
             if m not in LEGIT[LEFT]]
    if stray:
        bad.append(f"{LEFT} has a channel surviving multiplicity control it may not move: {stray}")
    if not G[RIGHT]["moved"]:
        bad.append(f"{RIGHT}'s nine did not move: {G[RIGHT]['delta']:+.4f} p {G[RIGHT]['p']:.4f}")
    if bad:
        raise SystemExit("F4 refuses to draw: its title says one arm stays in the channels it may move "
                         "and the other does not. Violations: " + "; ".join(bad))

    # Order by the deeper of the two, so the channels that carry the movement sit at the top of both.
    metrics = sorted(set(D[LEFT]) & set(D[RIGHT]), key=lambda m: min(D[LEFT][m], D[RIGHT][m]))
    ys = list(range(len(metrics)))
    # One scale for both panels, so a bar on the left and a bar on the right are the same length for the
    # same z. Asserted below, because two panels drawn to two scales is the whole defect this replaces.
    lo = min(v for d in D.values() for v in d.values())
    hi = max(v for d in D.values() for v in d.values())

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(5.2, 2.95), sharey=True, sharex=True,
                                   gridspec_kw={"wspace": 0.13})
    vlabels = []   # the per-bar value labels, kept so the fitting pass below measures those and not the headers
    for ax, t, cleg, cleak in ((axL, LEFT, C_LEGIT, C_LEAK), (axR, RIGHT, C_LEGIT_R, C_LEAK_R)):
        ax.axvline(0, color="#5b6770", lw=0.7, zorder=3)
        for y, m in zip(ys, metrics):
            v = D[t][m]
            ax.barh(y, v, color=cleg if m in LEGIT[t] else cleak, height=0.66, zorder=2, linewidth=0)
            # Signed, because on a signed axis they have to be: the mirrored design this replaces drew
            # magnitude outward and printed abs(v), which spelled T1's +0.049 and its -0.049 the same
            # way and left the sign to be inferred from which side of the rule the bar sat on. Three
            # places, because two rounds a real +0.005 to the +0.00 that three other channels have
            # exactly. An exact zero drops the sign entirely: it negates to -0.0, and "-0.000" reads as
            # a movement too small to see rather than as none at all.
            ha = "right" if v < 0 else "left"
            off = (hi - lo) * (-0.012 if v < 0 else 0.012)
            vlabels.append((ax, ax.text(v + off, y, "0.000" if v == 0 else sgn(v, 3), ha=ha,
                                        va="center", fontsize=PT_ANN, color="#14181c", zorder=4)))
        ax.set_title(NICE[t], fontsize=PT_LAB, fontweight="bold", loc="left", pad=11,
                     color=cleak)
        g = G[t]
        # In the panel's own dark hue, which is the hue of the bars this number is the group of. Grey for
        # both, with the same wording on each side, made the two stats read as one duplicated run of text.
        ax.text(0.0, 1.012, f"{g['n']} dark channels {sgn(g['delta'], 3)}, p {g['text']}",
                transform=ax.transAxes, ha="left", va="bottom", fontsize=PT_ANN, color=cleak)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="y", length=0)

    axL.set_yticks(ys)
    # Bold marks a channel neither edit may move, which is the same nine in both panels, so the label
    # column carries the convention once for both.
    axL.set_yticklabels([SHORT[m] for m in metrics], fontsize=PT_TICK)
    for lab, m in zip(axL.get_yticklabels(), metrics):
        if m not in LEGIT[LEFT] or m not in LEGIT[RIGHT]:
            lab.set_fontweight("bold")
    axL.set_ylim(len(metrics) - 0.4, -0.6)
    fig.supxlabel("median Δ per channel (z), one scale for both panels", fontsize=PT_LAB, y=0.015)
    # Stated as a rule, not as swatches. A two-patch key can only show one hue, and the convention runs
    # across two (blue for T1, green for T3), so blue swatches would have been describing the green
    # panel with the wrong colour.
    fig.text(0.5, -0.030, "dark fill and bold label = a channel outside the edit's licence; "
                          "pale = a licensed channel", ha="center", va="top", fontsize=PT_ANN, color="#3d474e")

    fig.suptitle("relocation stays in its licensed channels; joining reaches three more",
                 fontsize=PT_TITLE, fontweight="bold", x=0.0, ha="left", y=1.055)

    # Room for the value labels, measured rather than guessed: a label at a bar tip is drawn outside the
    # bar, so the deepest bar's label is the thing that leaves the axes, and its width depends on the
    # face and the number. Expanded until every label is inside, then asserted.
    #
    # Overflow is measured in ink and not in data units, because widening the scale also widens what a
    # label of fixed width covers in data units, so the two chase each other down to an asymptote: the
    # worst overflow here falls 0.093 -> 0.0099 -> 0.0011 -> 0.0001 and never reaches zero. Demanding
    # exact containment therefore fails on a figure that fits, which is what it did. Half a pixel at the
    # figure's own resolution is below the width of a stem at any size this is printed at, so a label
    # over the line by less than that puts no ink outside the axes.
    for _ in range(12):
        fig.canvas.draw()
        over, px_per_data = 0.0, None
        for ax, txt in vlabels:
            box, tb = ax.get_window_extent(), txt.get_window_extent()
            over = max(over, box.x0 - tb.x0, tb.x1 - box.x1)
            px_per_data = box.width / (ax.get_xlim()[1] - ax.get_xlim()[0])
        if over <= 0.5:
            break
        x0, x1 = axL.get_xlim()
        grow = over / px_per_data * 1.25
        axL.set_xlim(x0 - grow, x1 + grow)
    else:
        raise SystemExit("F4: the per-channel value labels will not fit inside the shared scale")
    if axL.get_xlim() != axR.get_xlim():
        raise SystemExit(f"F4: the two panels ended on different scales, {axL.get_xlim()} against "
                         f"{axR.get_xlim()}; a bar in one would not mean what it means in the other")

    # A figure wider than the column it is placed in fails silently: \includegraphics[width=\textwidth]
    # scales an oversized figure DOWN, so every point size declared above becomes a smaller number on the
    # page and the type is illegible for a reason nothing else reports.
    placed = fig.get_tightbbox(fig.canvas.get_renderer()).width + 0.04
    if placed > WIDTH_IN + 0.01:
        raise SystemExit(f"F4: tight width {placed:.3f}in exceeds the {WIDTH_IN}in text column, so "
                         f"LaTeX will scale the figure to {WIDTH_IN / placed:.3f} of drawn size and "
                         f"every declared point size is wrong. Shorten the title.")

    fig.savefig(f"{OUT}/F4.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F4.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F4.pdf and F4.png")
    print(f"channels drawn: {len(metrics)}; shared scale {axL.get_xlim()[0]:+.3f} to "
          f"{axL.get_xlim()[1]:+.3f}; signs drawn, not assumed")
    print(f"placed width {placed:.3f}in of {WIDTH_IN}in available")
    for t in (LEFT, RIGHT):
        g = G[t]
        print(f"  {t}: licensed " + ", ".join(f"{m} {D[t][m]:+.3f}" for m in sorted(LEGIT[t])))
        print(f"      the {g['n']} it may not move, as a group: {g['delta']:+.4f}, "
              f"p {g['text']} -> {'moved' if g['moved'] else 'not distinguishable'}")
        # Kept as a diagnostic, not a headline: which channels carry the group's movement. The old
        # -0.14 count was this list's length, which is why it is printed and not drawn.
        leak = sorted(((m, v) for m, v in D[t].items() if m not in LEGIT[t]), key=lambda kv: kv[1])
        print("      deepest of those: " + ", ".join(f"{m} {v:+.3f}" for m, v in leak[:4]))
        print(f"      surviving multiplicity control: one-sided {pn[t]['leaks_bh_q05'] or 'none'}, "
              f"two-sided {pn[t]['leaks_bh_q05_two_sided'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

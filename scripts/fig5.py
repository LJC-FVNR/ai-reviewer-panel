#!/usr/bin/env python3
"""F5: the second roster's three claims, drawn. Appendix H's figure.

File names in figs/ are creation order, not document order. This one sits in Appendix H, after the two figures
already there, so the document numbers it last; audit_submission.py derives the numbering from the markdown
order and compares it against what LaTeX typesets, so the mismatch is checked rather than remembered.

The roster -- eight slots over six vendors, no model shared with the five-model instrument, a checksum-identical
prompt, the same sixteen published papers -- was run as the replication three sections lean on, and reached the
reader as a table row and three prose sentences. Its grade result is now the lower half of Figure 2(a). The
three claims that were left without a surface are here.

(a) Order survives the swap and level does not. The sixteen papers on the two rosters' own composites, each
    calibrated against its own corpus, with the identity line. The correlation is the claim; the level shift is
    a panel-against-panel quantity, so it is printed rather than drawn as a distance, and it is printed against
    both rosters' re-run bands because it clears one and not the other.

(b) Why adding vendors does not repair reviewer variance: the slots' severity, grouped by the vendor that
    served them. Six vendor rows carry the eight slots of this roster and the five of the instrument, so both
    the vendor grouping and the leniency spread of each roster are read off one axis. Three of these slots are
    one vendor at three sizes, which is what makes the vendor share of the between-slot variance estimable at
    all, and their span against the extremes is annotated for exactly that reason.

(c) The presentation arms on this roster, slot by slot: the median composite move each slot returns for each
    transform, against zero and against this roster's own re-run band. The pooled figures and the count of
    slots moving down are the claims; the per-slot points are what they are made of.

Every value comes from n0_analysis.json and n2_analysis.json, which the bundle ships. Nothing here is
recomputed from reviews: a figure that re-derived a published number would be a second implementation of it.

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
from matplotlib.lines import Line2D

WS = "/path/to/workspace"
AN = f"{WS}/ai_native_academia"
N0 = f"{AN}/n0_cursor8_iclr/n0_analysis.json"
N2 = f"{AN}/n2_pia_cursor8/n2_analysis.json"
OUT = f"{AN}/figs"

PT_TITLE, PT_LAB, PT_TICK, PT_ANN = 8.0, 7.5, 7.0, 6.4
FONT = "Arimo"
C_EIGHT, C_FIVE = "#08519c", "#d94801"
INK, MUTE, BAND = "#14181c", "#3d474e", "#dfe6ec"
# The five-model roster's vendor per slot, as package_release.py writes it into the released spec: the two
# codex slots are OpenAI models and the three claude slots Anthropic ones. It is the roster's identity rather
# than a measurement, and no working-tree file states it.
VENDOR_FIVE = {"R1": "openai", "R2": "openai", "R3": "anthropic", "R4": "anthropic", "R5": "anthropic"}
# The vendors as a reader writes them. The key is the slug the spec groups by, which is a machine's spelling of
# a company name: printed straight onto the axis it labelled six rows `openai`, `anthropic`, `xai` and read as
# an API identifier rather than as the firms the roster is spread across. Every slug the data carries has to be
# in here, so a seventh vendor stops the figure instead of appearing in the wrong register.
VENDOR_NICE = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
               "xai": "xAI", "zhipu": "Zhipu", "moonshot": "Moonshot"}
# The transforms under the names the paper gives them, and the marker each keeps across the panel. T2 is the
# comparison scale rather than a presentation arm -- it withdraws a claim, so a reviewer may correctly mark it
# down -- and it is drawn open for that reason.
TRANS = [("T1_endmatter", "T1 figures at end", "o", True),
         ("T3_lengthen", "T3 sentences joined", "s", True),
         ("T2_concede", "T2 claim withdrawn, the scale", "D", False)]

plt.rcParams.update({
    "font.family": FONT, "font.size": PT_TICK,
    "mathtext.fontset": "custom", "mathtext.rm": FONT, "mathtext.sf": FONT,
    "mathtext.it": f"{FONT}:italic", "mathtext.bf": f"{FONT}:bold",
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "pdf.fonttype": 42,
})


def main():
    os.makedirs(OUT, exist_ok=True)
    d = json.load(open(N0))
    n2 = json.load(open(N2))
    sw = d["roster_swap"]
    sev8 = d["mean_recommendation_by_slot"]
    sev5 = d["five_model_recomputed"]["slot_means"]
    ven8 = d["vendor_of_slot"]
    disp = {k: (v.rsplit(" ", 1)[0] if v.endswith((" High", " Max")) else v)
            for k, v in d["slot_display"].items()}

    fig = plt.figure(figsize=(5.5, 3.95))
    # Two rows: the two sixteen-paper panels above, and the presentation arms across the full width below,
    # where eight rows of three transforms need the width more than they need to sit beside anything.
    # The rows get one grid each because their left margins differ. A margin is a fraction of the canvas and
    # matplotlib reserves no room for tick labels, so the margin has to hold the widest label of the row
    # INSIDE the figure box -- panel (c)'s slot names are three times the width of panel (a)'s "-1.0", and a
    # single margin wide enough for them would spend a fifth of panel (a) on white space. With one margin
    # for both rows the labels hung off the left edge, the tight bounding box grew to hold them, and the
    # saved figure came out over the text width, which md2tex.py would then place at its drawn size.
    # Annotations are kept inside their own axes for the same reason: at 6.4 pt a line of about ninety
    # characters is already wider than the whole canvas.
    gs_t = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.05],
                            left=0.105, right=0.988, top=0.930, bottom=0.590, wspace=0.55)
    gs_b = fig.add_gridspec(1, 1, left=0.178, right=0.988, top=0.455, bottom=0.085)
    axA, axB = fig.add_subplot(gs_t[0, 0]), fig.add_subplot(gs_t[0, 1])
    axC = fig.add_subplot(gs_b[0, 0])

    # ---- (a) the order survives the swap ---------------------------------------------------------------
    xs = [v[0] for v in sw["pairs"].values()]
    ys = [v[1] for v in sw["pairs"].values()]
    lim = [min(xs + ys) - 0.20, max(xs + ys) + 0.20]
    axA.plot(lim, lim, color="#8c99a4", lw=0.7, ls=(0, (3.5, 2.2)), zorder=1)
    axA.scatter(xs, ys, s=16, c=C_EIGHT, linewidths=0.5, edgecolors="white", zorder=3)
    axA.set_xlim(lim)
    axA.set_ylim(lim)
    # Both axes carry the same quantity over the same range, so they take the same ticks in the same format;
    # left to itself matplotlib gives one axis a decimal and the other an integer, which reads as two scales.
    tk = [t for t in (-1.0, -0.5, 0.0, 0.5, 1.0) if lim[0] <= t <= lim[1]]
    axA.set_xticks(tk)
    axA.set_yticks(tk)
    axA.set_xticklabels([sgn(t, 1, plus=False) for t in tk])
    axA.set_yticklabels([sgn(t, 1, plus=False) for t in tk])
    axA.set_xlabel("five-model composite (z)", fontsize=PT_LAB)
    axA.set_ylabel("eight-slot composite (z)", fontsize=PT_LAB)
    axA.set_title("a  the order is the papers'", fontsize=PT_TITLE, fontweight="bold", loc="left", pad=5)
    axA.tick_params(labelsize=PT_TICK)
    for s in ("top", "right"):
        axA.spines[s].set_visible(False)
    axA.text(0.04, 0.97, f"ρ = {sgn(sw['rho'], 3)}", transform=axA.transAxes,
             ha="left", va="top", fontsize=PT_ANN, color=INK, zorder=4)
    axA.text(0.04, 0.885, rng(*sw["ci"], 3), transform=axA.transAxes,
             ha="left", va="top", fontsize=PT_ANN, color=INK, zorder=4)
    # The other half of the claim. It clears the tighter roster's band and not the looser one, which is the
    # comparison the appendix makes and the only one the numbers support; the assertion is here so that a
    # rescore flattening the gap would stop the build rather than leave the annotation asserting it.
    tight, loose = sorted((sw["median_rerun_five"], sw["median_rerun_this"]))
    assert tight < sw["median_swap"] < loose, (tight, sw["median_swap"], loose)
    axA.text(0.97, 0.03,
             f"level shift {sw['median_swap']:.3f} z,\npast this roster's band\n({tight:.3f}), inside the\n"
             f"five-model band ({loose:.3f})",
             transform=axA.transAxes, ha="right", va="bottom", fontsize=PT_ANN,
             color=INK, linespacing=1.35, zorder=4)

    # ---- (b) severity is a vendor's ---------------------------------------------------------------------
    vmean = d["vendor_nested"]["vendor_means"]
    vorder = sorted(vmean, key=lambda v: vmean[v])
    ypos = {v: i for i, v in enumerate(vorder)}
    # The two rosters are offset symmetrically about the row's grid line, so a marker's row is never in
    # doubt: an asymmetric pair reads as belonging to whichever label it sits nearer.
    ptsB = []
    for s_, sv in sev8.items():
        ptsB.append((sv, ypos[ven8[s_]] - 0.17))
        axB.scatter([sv], [ypos[ven8[s_]] - 0.17], s=17, c=C_EIGHT, linewidths=0.5,
                    edgecolors="white", zorder=3)
    for s_, sv in sev5.items():
        ptsB.append((sv, ypos[VENDOR_FIVE[s_]] + 0.17))
        axB.scatter([sv], [ypos[VENDOR_FIVE[s_]] + 0.17], s=17, marker="^", facecolors="none",
                    edgecolors=C_FIVE, linewidths=0.8, zorder=3)
    axB.set_yticks(range(len(vorder)))
    seen = set(vorder) | set(VENDOR_FIVE.values())
    assert seen <= set(VENDOR_NICE), f"F5: unnamed vendor slug {sorted(seen - set(VENDOR_NICE))}"
    axB.set_yticklabels([VENDOR_NICE[v] for v in vorder], fontsize=PT_ANN)
    # Headroom for the legend only. The three-line annotation used to sit here too and printed straight
    # through it: two blocks anchored to the same corner of an axis do not know about each other.
    axB.set_ylim(len(vorder) + 1.85, -1.70)
    axB.set_xlabel("slot's mean recommendation (1–10)", fontsize=PT_LAB)
    axB.set_title("b  severity is a vendor's", fontsize=PT_TITLE, fontweight="bold", loc="left", pad=5)
    axB.tick_params(labelsize=PT_TICK)
    axB.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)
    axB.grid(axis="y", color="#eef1f4", lw=0.6, zorder=0)
    sp8 = max(sev8.values()) - min(sev8.values())
    sp5 = max(sev5.values()) - min(sev5.values())
    within = d["vendor_nested"]["within_vendor_spread"]
    multi = max(within, key=lambda v: within[v])
    # Below the last row rather than beside it: written into the rows it crossed the grid lines of the two
    # it sat on, and a line of text through a row rule reads as a row of its own.
    axB.text(0.02, 0.02, f"{d['vendor_nested']['vendor_share_of_slot']:.1f}% of the between-slot variance\n"
                         f"is between vendors, and {VENDOR_NICE[multi]}'s\n"
                         f"three sizes sit {within[multi]:.2f} apart",
             transform=axB.transAxes, ha="left", va="bottom", fontsize=PT_ANN,
             color=INK, linespacing=1.3, zorder=4)
    legB = axB.legend(handles=[Line2D([], [], marker="o", ls="none", ms=3.4, mfc=C_EIGHT, mec="white",
                               label=f"8 slots, 6 vendors: {sp8:.2f} apart"),
                        Line2D([], [], marker="^", ls="none", ms=3.6, mfc="none", mec=C_FIVE,
                               mew=0.8, label=f"5 slots, 2 vendors: {sp5:.2f} apart")],
               loc="upper right", bbox_to_anchor=(1.01, 1.02), frameon=False, fontsize=PT_ANN,
               handlelength=1.0, labelspacing=0.30, borderpad=0.0, handletextpad=0.4)

    # ---- (c) the presentation arms, slot by slot --------------------------------------------------------
    band = n2["rerun_band_this_roster"]
    order = sorted(sev8, key=lambda s_: sev8[s_])
    axC.axvspan(-band, band, color=BAND, lw=0, zorder=0)
    axC.axvline(0, color="#8c99a4", lw=0.7, zorder=1)
    ptsC = []
    for key, lab, mk, filled in TRANS:
        per = n2["transforms"][key]["per_slot"]
        ptsC += [(per[s_]["median_delta"], j) for j, s_ in enumerate(order)]
        axC.scatter([per[s_]["median_delta"] for s_ in order], list(range(len(order))),
                    s=17, marker=mk, zorder=3,
                    c=(C_EIGHT if filled else "none"),
                    edgecolors=("white" if filled else MUTE), linewidths=(0.5 if filled else 0.8),
                    label=lab)
    # Room at the right-hand end for the key, so that it sits beside the points instead of on top of the
    # two it covered when it was placed inside the data range -- the check below is what reported them.
    xlo, xhi = min(x for x, _ in ptsC), max(x for x, _ in ptsC)
    axC.set_xlim(xlo - 0.05, xhi + 0.34)
    axC.set_yticks(range(len(order)))
    axC.set_yticklabels([f"{s_}  {disp[s_]}" for s_ in order], fontsize=PT_ANN)
    axC.set_ylim(len(order) - 0.4, -1.9)
    axC.set_xlabel("median Δ composite from the untouched paper (z)", fontsize=PT_LAB)
    axC.set_title("c  a rewrite that preserves every result moves this roster too", fontsize=PT_TITLE,
                  fontweight="bold", loc="left", pad=5)
    axC.tick_params(labelsize=PT_TICK)
    axC.tick_params(axis="y", length=0)
    for s in ("top", "right", "left"):
        axC.spines[s].set_visible(False)
    t1, t3 = n2["transforms"]["T1_endmatter"], n2["transforms"]["T3_lengthen"]
    axC.text(0.0, -1.72,
             f"shaded: this roster's own re-run band, ±{band:.3f} z\n"
             f"pooled over the eight papers, {sgn(t1['median_delta'], 3)} for T1 and "
             f"{sgn(t3['median_delta'], 3)} for T3, which is lower in "
             f"{t3['slots_negative']} of the {len(order)} slots",
             transform=axC.get_yaxis_transform(), ha="left", va="top", fontsize=PT_ANN,
             color=INK, linespacing=1.35, zorder=4)
    # Inside the axes, bottom right. Above the panel it collided with the title, which is the longer of the
    # two and the one a reader needs first; the lowest rows are the slots this rewrite moved down, so the
    # corner it takes is empty.
    # On an opaque white ground, because a key sitting among the points is otherwise read as three more of
    # them. The corner it occupies is asserted empty below rather than judged by eye.
    legC = axC.legend(loc="lower right", bbox_to_anchor=(1.0, 0.01), frameon=True, facecolor="white",
                      edgecolor="none", framealpha=1.0,
                      fontsize=PT_ANN, handlelength=1.0, labelspacing=0.32, borderpad=0.25,
                      handletextpad=0.4)

    # A legend is drawn over the data area in both of the lower two panels, one of them on an opaque
    # ground, so what would otherwise be an eye check is a measurement: no plotted point may fall inside a
    # legend's box. A key that hides a point removes exactly the observation it claims to identify.
    fig.canvas.draw()
    rnd = fig.canvas.get_renderer()
    for nm, ax, leg, pts in (("b", axB, legB, ptsB), ("c", axC, legC, ptsC)):
        bb = leg.get_window_extent(rnd)
        hidden = [pt for pt in pts if bb.contains(*ax.transData.transform(pt))]
        assert not hidden, f"panel ({nm}): legend covers {hidden}"

    fig.savefig(f"{OUT}/F5.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(f"{OUT}/F5.png", dpi=380, bbox_inches="tight", pad_inches=0.02)
    print(f"wrote {OUT}/F5.pdf and F5.png")

    # ---- what the panels assert, printed so the caption can be checked against them --------------------
    print(f"(a) {len(xs)} papers, rho {sw['rho']:+.4f} CI {sw['ci']}, drop-one {sw['drop_one']}; "
          f"level shift {sw['median_swap']:.4f} z, bands {tight:.4f} (eight) and {loose:.4f} (five); "
          f"clears the tighter only: {tight < sw['median_swap'] < loose}")
    print(f"(b) vendor share of between-slot variance "
          f"{d['vendor_nested']['vendor_share_of_slot']:.3f}%; vendor means {vmean}")
    print(f"    spreads: eight-slot {sp8:.3f} ({min(sev8.values()):.2f}-{max(sev8.values()):.2f}), "
          f"five-model {sp5:.3f} ({min(sev5.values()):.2f}-{max(sev5.values()):.2f}); "
          f"within-vendor {within}")
    for key, lab, _, _ in TRANS:
        t = n2["transforms"][key]
        print(f"(c) {lab:<30} pooled {t['median_delta']:+.4f}, {t['slots_negative']} of 8 slots down, "
              f"|delta|/band {t['abs_delta_over_own_band']:.3f}, papers down {t['n_negative']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

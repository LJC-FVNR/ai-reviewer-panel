#!/usr/bin/env python3
"""F0, the opening figure: what the instrument is, and what it tells an author who runs it.

Numbered 0 because it sits before the three claim figures, whose scripts and expectation rows are already
keyed to 1 through 4. On the page LaTeX numbers by order of appearance, so this is Figure 1 and F1.pdf is
Figure 2; the file names track the scripts, not the page.

The paper had no method figure. Every fact a reader needs in order to know WHAT was measured -- how many
slots, which models, how a paper becomes a number, what the number is relative to -- was in prose only, and
a reader who does not already know the internal structure could not reconstruct it. Panel (a) is that
structure, drawn as the run flow, so the composition, the retrieval and the scoring are readable without
§2. Panel (b) is the readout the flow produces: the reference field, the declined papers, and one of those
declined papers drawn again in that distribution with its own band, which is the form the instrument takes
when an author rather than a venue is asking.

That focal marker was the submitting manuscript's own score for thirteen builds. It came out together with
the appendix passages and the reflexivity note that reported the same scores in prose: what is left says
that no manuscript of ours is in the scored corpora or described as study material, and a labelled marker in
the opening figure would have contradicted that in the one exhibit every reader sees. A paper from the
corpus does the same work, is checkable against the bundle, and needs no disclosure to explain it. Which
corpus paper is not a choice made here: it is the declined submission the panel puts highest, so the
selection is a line of code rather than a preference.

(b) carries its own resolution limit on the panel, next to the ranking it qualifies. A distribution with a
marker in it invites the reader to take the rank seriously to the last digit, and the whole finding of §2
and §5 is that this instrument cannot support that. Drawing the re-run band as the marker's error bar puts
the qualification where the over-reading would happen, rather than in a caption the reader has left behind.

EVERY NUMBER HERE IS RECOMPUTED, not read from a stored field. The calibration file also carries
per-paper composites, rounded to four decimals, and reading those would put the field maximum on this
figure at +1.093 while Appendix G prints +1.094 from a full-precision recomputation. Nobody would see the
marker move by four ten-thousandths of a z; a reader comparing the annotation with the appendix would see
the paper disagree with its own figure. So the composite is rebuilt from the shipped reviews through
reproduce.py's own definition, which is the definition every expectation row checks.

Drawn at final placed size (5.5in = NeurIPS text width), so the type sizes here are the type sizes on the
page.
"""
from __future__ import annotations

import io
import os
import json
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import sgn  # noqa: E402
# The composite, the band and the field are defined once, in the file that checks them against the page.
from reproduce import composites, load  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from matplotlib.transforms import offset_copy
from matplotlib.text import Text

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/figs"
B = HERE if os.path.isdir(f"{HERE}/reviews") else f"{HERE}/release/aina2026_agent_reviewers"

PT_TITLE, PT_LAB, PT_TICK, PT_ANN, PT_FINE = 8.0, 7.5, 7.0, 6.4, 6.2
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

INK = "#14181c"        # body text on paper
MUTE = "#4a555e"       # secondary text, still 7:1 on white
RULE = "#8d9aa3"
# A shade darker than the rule above, for (c)'s median ticks: they are drawn over the papers rather than
# behind them, so the rule's value read as one more pale mark among sixteen.
TICK_C = "#6f7d87"
ACC = "#08519c"        # the published field, and the accepted end of F1's ramp
REJ = "#d94801"        # the declined papers, matching F1's lower-rated arm
# The same hue, darkened until it clears 4.5:1 as type on paper, on the box and on the shaded span. The marker
# keeps the lighter value because a marker is a shape: it has to match F1's ramp, and the floor is about glyphs.
REJ_TXT = "#b83c00"
FOC = "#7a1b6d"       # the focal paper: a third hue, so its two readings are not a third population
BOXFC = "#eef2f5"
BOXEC = "#b9c4cc"


# One line's advance in the run flow, in inches, and the panel is sized to fit rather than the other way
# round. These were axes fractions of a panel of fixed height, which is the same thing only while the panel's
# height never changes: a fraction times a height is a leading, so adding a line to one box either overflows
# the panel or, if the panel is grown to hold it, loosens the leading of all four boxes at once. In inches the
# leading is what it says it is -- about 1.2 times the 6.2 pt type for a plain line, 1.33 for a heading-like
# one -- and the panel's height is computed from the tallest box below.
ADV_IN = {"body": 0.1145, "key": 0.1145, "fine": 0.1030, "gap": 0.0644}
HEAD_IN = 0.2218  # from the top of the box to the first line's centre, leaving room for the bold header
TAIL_IN = 0.0429  # from the last line's centre to the bottom of the box
GEOM = {"h_a": 1.0}  # panel (a)'s height in inches, set in main() once the boxes are measured


def stage_height_in(lines):
    """-> the box height these lines need, in inches."""
    return HEAD_IN + sum(ADV_IN[ln[1]] for ln in lines) + TAIL_IN


def frac(inches):
    """-> that many inches as a fraction of panel (a)'s height, which is what the drawing code works in."""
    return inches / GEOM["h_a"]


def stage_height(lines):
    """-> the box height these lines need, so a box is never asked to hold more than it has room for."""
    return frac(stage_height_in(lines))


STAGES = [
    (0.000, 0.2245, "1  retrieve", [
        ("every ICLR 2026", "body"),
        ("submission: 19,814,", "body"),
        ("with the venue's own", "fine"),
        ("decisions and ratings", "fine"),
        ("", "gap"),
        # Only the 32 declined papers are one primary area by design. The accepted 16 are area-mixed, so the
        # area restriction is stated of the declined sets alone, as Section 3 and Appendix D state it.
        ("three sets of 16, the", "fine"),
        ("declined from one area:", "fine"),
        ("accepted", "key", ACC),
        ("declined, higher-rated", "key", REJ_TXT),
        ("declined, lower-rated", "key", REJ_TXT),
    ]),
    (0.2585, 0.4830, "2  read", [
        ("one review is one fresh,", "body"),
        ("isolated prompt", "body"),
        ("", "gap"),
        ("it sees the paper's", "fine"),
        ("text, cut at the", "fine"),
        ("reference list, and", "fine"),
        ("the rubric", "fine"),
        ("", "gap"),
        ("never the authors, the", "fine"),
        ("venue's decision, or", "fine"),
        ("any other review", "fine"),
    ]),
    # Both rosters, by vendor. This box listed the five model names of one roster, and the second roster
    # appeared nowhere except a grey line under the flow, so the figure showed a panel of two vendors and a
    # reader was entitled to read the whole design as two vendors marking their own kind. The replication is
    # eight slots from six vendors and it carries every result in the paper, which is the answer to that
    # reading and was the one thing the opening figure did not say. What pays for the room is the model
    # names: a version number is not what a reader is checking here, and the roster tables in the appendix
    # give them in full. So the count of slots and the vendors behind them, which is what the objection is
    # about, and one line each for what a paper costs on each roster.
    (0.5170, 0.7415, "3  the panel", [
        ("two rosters, each slot", "body"),
        ("a fixed model and effort", "body"),
        ("", "gap"),
        ("A  5 slots, 2 vendors:", "key"),
        ("OpenAI, Anthropic", "fine"),
        ("10 reviews per paper", "fine"),
        ("", "gap"),
        ("B  8 slots, 6 vendors:", "key"),
        ("OpenAI, Anthropic,", "fine"),
        ("Google, xAI,", "fine"),
        ("Moonshot, Zhipu", "fine"),
        ("16 reviews per paper", "fine"),
    ]),
    (0.7755, 1.0000, "4  score", [
        # Same defect twice over in three lines: the old breaks cut "1 to 10" and "1 of 5" apart, so the
        # box opened on "12 rated qualities, 1" and closed on a bare "grades". Both ranges now sit whole.
        ("12 rated qualities,", "body"),
        ("1 to 10, and 1 of 5", "body"),
        ("grades", "body"),
        ("", "gap"),
        ("each model's mark for", "fine"),
        ("each quality is put in", "fine"),
        ("standard units of the", "fine"),
        ("16 accepted papers,", "fine"),
        ("then averaged", "fine"),
        ("", "gap"),
        ("one composite, in z", "key", FOC),
    ]),
]


PLACED = []  # (artist, box x0, box x1) for the fit check below
FRAMES = []  # (patch, header) for the frame check below


def stage(ax, x0, x1, header, lines, height, top=0.985):
    """One column of the run flow: a titled box with left-aligned lines, drawn back to front.

    The height is passed in rather than fixed, and the caller passes the same one to every column so the
    four boxes align. Overflow used to be silent: the box was drawn at a fixed size and the lines were
    written downward past its edge, which put two columns' last lines outside the box and on top of panel
    (b)'s title. It also pushed the figure to 7.75in wide, half again the text width it is drawn at, so the
    page would have rescaled every type size on it. Nothing in the repository could see either of those,
    because a figure has no notion of a full box, so the two checks here are the check: the height
    assertion below, and check_fit, which measures every line against the box that is supposed to hold it.
    """
    need = stage_height(lines)
    assert need <= height + 1e-9, f"{header!r} needs {need:.3f} of the panel and was given {height:.3f}"
    y1, y0 = top, top - height
    # clip_on=False, because a patch on an axes is clipped to that axes and the first and last of these boxes
    # are drawn flush with the panel's edges. The rounded box style pads outward, so both outer strokes fell
    # outside the clip and neither was drawn: the run flow went out with two of its eight sides missing, and
    # every check here was measuring text against a box edge that is not on the page. The saved figure takes a
    # tight bounding box, which grows to hold ink and cannot cut it, so the stroke is safe outside the axes.
    box = FancyBboxPatch(
        (x0, y0), x1 - x0, height, boxstyle="round,pad=0.004,rounding_size=0.012",
        transform=ax.transAxes, fc=BOXFC, ec=BOXEC, lw=0.6, zorder=1, clip_on=False)
    ax.add_patch(box)
    FRAMES.append((box, header))
    PLACED.append((ax.text(x0 + 0.012, y1 - frac(0.0887), header, transform=ax.transAxes, ha="left",
                           va="center", fontsize=PT_LAB, fontweight="bold", color=INK, zorder=3),
                   x0, x1))
    y = y1 - frac(HEAD_IN)
    for text, kind, *rest in lines:
        if kind == "gap":
            y -= frac(ADV_IN["gap"])
            continue
        fs = PT_FINE
        # A line may name its own colour. Three lines do, and they are the three that also appear in panel (b):
        # naming a set in the colour (b) draws it in is what tells a reader which strip is which, and it is the
        # only thing in the figure that connects the retrieval to the readout without a sentence.
        col = rest[0] if rest else (INK if kind in ("body", "key") else MUTE)
        PLACED.append((ax.text(x0 + 0.012, y, text, transform=ax.transAxes, ha="left", va="center",
                               fontsize=fs, color=col,
                               fontweight="bold" if kind == "key" else "normal",
                               zorder=3, linespacing=1.05), x0, x1))
        y -= frac(ADV_IN[kind])
    return y0


def check_fit(fig, ax, margin=0.006):
    """Every line of the run flow must sit inside the box drawn around it, measured, not judged by eye.

    At 6 pt a line that overruns its box by a couple of points is invisible on a whole-figure look and
    obvious once the page is printed, and the failure it produces is text on top of a box edge. So the
    widths are measured from the renderer after a draw and compared against the box the line was filed
    under. `margin` is the inset the text is placed at, less a hair for the rounding of the box corner.
    """
    fig.canvas.draw()
    inv = ax.transAxes.inverted()
    bad = []
    for art, x0, x1 in PLACED:
        bb = inv.transform(art.get_window_extent(fig.canvas.get_renderer()).get_points())
        if bb[1][0] > x1 - margin:
            bad.append(f"{art.get_text()!r} reaches {bb[1][0]:.4f}, past its box edge at {x1:.4f}")
    assert not bad, "run-flow text does not fit its box:\n  " + "\n  ".join(bad)


def check_frames(fig, dpi=200, reach_pt=1.2):
    """Every run-flow box shows both of its vertical strokes, read back as pixels.

    Whether a box is drawn is not a property of the code that asks for one. A patch belongs to an axes and is
    clipped to it, the first and last of these boxes sit flush with the panel's edges, and the rounded style
    pads outward, so for several builds both outer strokes were clipped away: the figure went out with two of
    the run flow's eight sides missing while every other check here passed, because a text-fits-its-box check
    reads the box out of the code rather than off the canvas.

    So the canvas is what this reads. Rendered without a tight bounding box, so that display coordinates and
    pixels agree; a tight box adds margin and cannot remove ink, so a side missing here is missing in the saved
    file too. The rows sampled are at a quarter and three quarters of the box height, away from the arrows,
    which enter at the middle exactly where the padded edge is and would answer for a stroke that is not there.
    A pixel counts as a stroke if it is darker than the box fill, since a 0.6 pt line lands between pixels and
    reaches neither its own colour nor the fill's.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    px = plt.imread(io.BytesIO(buf.getvalue()))[:, :, :3] * 255
    darker = (px <= np.array([int(BOXFC[i:i + 2], 16) for i in (1, 3, 5)]) - 6).all(axis=2)
    H, W = darker.shape
    s, bad = dpi / fig.dpi, []
    reach = max(2, round(reach_pt * dpi / 72))
    for box, header in FRAMES:
        (x0, y0), (x1, y1) = box.get_window_extent(fig.canvas.get_renderer()).get_points()
        rows = [H - round((y0 + f * (y1 - y0)) * s) for f in (0.25, 0.75)]
        for side, x in (("left", x0), ("right", x1)):
            col = round(x * s)
            span = range(max(0, col - reach), min(W, col + reach + 1))
            if not all(any(darker[r, c] for c in span) for r in rows if 0 <= r < H):
                bad.append(f"{header!r} has no {side} edge on the canvas: nothing drawn within "
                           f"{reach_pt} pt of x={col} of {W} px")
    assert not bad, "a run-flow box is missing a side:\n  " + "\n  ".join(bad)


def arrow(ax, x0, x1, y):
    ax.add_patch(FancyArrowPatch(
        (x0, y), (x1, y), transform=ax.transAxes, arrowstyle="-|>,head_width=1.6,head_length=2.6",
        lw=0.8, color=MUTE, shrinkA=0, shrinkB=0, mutation_scale=1.0, zorder=2))


def check_clear(fig, ax, texts, markers, pad_pt=1.4, pairs=True):
    """Nothing in panel (b) may be drawn on the data it describes, or on anything else drawn there.

    The first version of this panel put all five of its labels on top of the markers: the row labels ran
    across the accepted papers, the threshold note sat in the same strip, and the two-line note under the
    target crossed the axis and its tick labels. None of that is visible on a whole-figure look, because at
    this size a label crossing a strip of 4 pt markers reads as one slightly heavier line of text. It took a
    magnified crop to see, which means the next such collision would ship. So the boxes are measured.

    Markers are treated as squares of their own diameter, which is generous at the corners and therefore
    conservative. `pad_pt` is the clearance demanded on every side, so passing means separated, not merely
    not touching.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pad = pad_pt * fig.dpi / 72.0

    def box(bb):
        return bb.x0 - pad, bb.y0 - pad, bb.x1 + pad, bb.y1 + pad

    def hit(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    # Text.get_window_extent, not the artist's own: an Annotation unions its leader line into its extent, and
    # a leader is drawn to touch the thing it points at, so measuring the artist would report every leader as
    # a collision with its own target and the real ones would be lost in the noise.
    labelled = [(f"{t.get_text().splitlines()[0][:34]!r}", box(Text.get_window_extent(t, r)))
                for t in texts]
    strips = []
    for xs, y, size_pt, what in markers:
        h = size_pt * fig.dpi / 144.0
        for x in xs:
            px, py = ax.transData.transform((x, y))
            strips.append((what, (px - h, py - h, px + h, py + h)))

    def gap(a, b):  # how far apart on each axis, negative meaning overlapping, in points
        f = 72.0 / fig.dpi
        return (max(a[0] - b[2], b[0] - a[2]) * f, max(a[1] - b[3], b[1] - a[3]) * f)

    bad = []
    for name, b in labelled:
        for what, m in strips:
            if hit(b, m):
                dx, dy = gap(b, m)
                bad.append(f"{name} is drawn on {what} (x by {-dx:.1f}pt, y by {-dy:.1f}pt)")
                break
    for i, (n1, b1) in enumerate(labelled if pairs else []):
        for n2, b2 in labelled[i + 1:]:
            if hit(b1, b2):
                bad.append(f"{n1} and {n2} overlap")
    assert not bad, "a panel is drawn on top of itself:\n  " + "\n  ".join(sorted(set(bad)))


def check_span(fig, ax, texts, slack_pt=1.0, margin_pt=3.0):
    """Panel (b)'s notes must stay inside the panel, measured rather than counted, at both ends.

    A note here is right-aligned at the axis's right end, so a longer sentence grows leftward and runs off the
    plotting area rather than being clipped. Nothing else would report that: the collision check only fires if
    the overrun happens to reach a marker or a row label, and the note that names the shaded range clears the
    label by about a fifth of an inch. Character counts are no help either -- the note is built from numbers
    whose widths change with their signs and digit counts, so the same wording measures differently from one
    run to the next. So the extent is read from the renderer and compared with the axes' own edges.

    The right edge is checked for a margin rather than for containment, and that asymmetry is the point. The
    left end of a note is interior to the figure, so touching the axes there is merely tight. The panel's right
    edge is within a few thousandths of the figure's own, and the saved file is cropped to its contents, so a
    note that ends exactly at the axis ends exactly at the trimmed edge of the page: its last two words sit
    against nothing. The version before this one had the whole first note flush to the paper's margin, and
    every check in this file passed on it, because containment is what they all tested.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ab = ax.get_window_extent(r)
    px = fig.dpi / 72.0
    bad = []
    for t in texts:
        bb = Text.get_window_extent(t, r)
        if bb.x0 < ab.x0 - slack_pt * px:
            bad.append(f"{t.get_text().splitlines()[0][:44]!r} starts {(ab.x0 - bb.x0) / px:.1f}pt left of the "
                       f"panel ({bb.width / ab.width * 100:.1f}% of the panel's width)")
        if bb.x1 > ab.x1 - margin_pt * px:
            bad.append(f"{t.get_text().splitlines()[0][:44]!r} ends {(bb.x1 - ab.x1) / px:+.1f}pt from the "
                       f"panel's right edge, inside the {margin_pt:.0f}pt the trimmed page needs")
    assert not bad, "panel (b) text runs off the panel:\n  " + "\n  ".join(bad)


def check_no_overlap(fig, depth_pt=0.6):
    """No two strings anywhere on the canvas may be drawn on top of each other.

    Every other check in this file is scoped to one panel, and this defect was between panels: (c)'s two
    explanatory lines were placed above their own title instead of below it and landed on (b)'s axis label,
    two greys at 6 pt printing over each other. Nothing fired. check_clear had been given (b)'s notes and
    (c)'s rows, and neither list contained the other panel's text, which is the failure mode of a check that
    takes a list -- it can only see what someone remembered to put in it.

    So nothing is listed here: every visible Text in the figure, tick labels and axis labels included, against
    every other. The test is a depth rather than a touch, because a line box carries leading the glyphs do not
    fill and the run flow's own lines are set tight enough that consecutive boxes graze each other. Overlap on
    both axes by more than a fraction of a point is ink on ink.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    px = fig.dpi / 72.0
    arts = [t for t in fig.findobj(Text) if t.get_text().strip() and t.get_visible()]
    boxes = [(t, Text.get_window_extent(t, r)) for t in arts]
    bad = []
    for i, (t1, b1) in enumerate(boxes):
        for t2, b2 in boxes[i + 1:]:
            dx = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
            dy = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
            if dx > depth_pt * px and dy > depth_pt * px:
                bad.append(f"{t1.get_text().splitlines()[0][:34]!r} and "
                           f"{t2.get_text().splitlines()[0][:34]!r} overlap by "
                           f"{dx / px:.1f} by {dy / px:.1f}pt")
    assert not bad, "two strings are drawn on each other:\n  " + "\n  ".join(sorted(set(bad)))


def _lum_rgb(rgb):
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def check_contrast(fig, floor=4.5):
    """Every string in the figure, against whatever is actually behind it, sampled from the render.

    Text is legible against what it is drawn on, not against the paper: panel (b) shades the published range
    and panel (a) sets its columns on a tinted box, so a figure that measures its colours against white
    passes while the reader is looking at the same ink on a fill. The earlier version of this check took a
    hand-written list of three pairs, which is the same thing as an exemption list -- it named the two notes
    inside the shading and the run-flow body, and therefore never looked at the three row labels in the
    gutter. One of those was under the floor on plain paper for as long as the check existed.

    So nothing is named here. Every Text artist is found, its own colour read, and its background taken from
    the figure rendered with all the text hidden, which is the only description of "behind it" that cannot
    fall out of date when a label moves.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    arts = [t for t in fig.findobj(Text) if t.get_text().strip() and t.get_visible()]
    boxes = [Text.get_window_extent(t, r) for t in arts]
    for t in arts:
        t.set_visible(False)
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].astype(float)
    for t in arts:
        t.set_visible(True)
    H = buf.shape[0]
    bad = []
    for t, bb in zip(arts, boxes):
        # A glyph is thin, so the mean over the box is mostly background even before the text is hidden; with
        # it hidden the median is the fill the string sits on, and the median rather than the mean so a marker
        # clipping one corner of the box cannot decide the answer.
        x0, x1 = int(max(bb.x0, 0)), int(min(bb.x1, buf.shape[1] - 1))
        y0, y1 = int(max(H - bb.y1, 0)), int(min(H - bb.y0, H - 1))
        if x1 <= x0 or y1 <= y0:
            continue
        back = np.median(buf[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3), axis=0) / 255.0
        ink = to_rgb(t.get_color())
        a, b = sorted((_lum_rgb(ink), _lum_rgb(back)))
        ratio = (b + 0.05) / (a + 0.05)
        if ratio < floor:
            bad.append(f"{t.get_text().splitlines()[0][:40]!r} is {ratio:.2f}:1 on the fill it sits on, "
                       f"under {floor}:1")
    assert not bad, "figure text is not legible where it sits:\n  " + "\n  ".join(sorted(set(bad)))


def channels(root, mu, sd, metrics, levels=1, pat="R?.json"):
    """-> {unit: {panel: {metric: z}}}: the same read the composite comes from, one level finer.

    reproduce.py's cells() averages the twelve metrics away inside zmean, because every quantity in the paper
    is a composite. Panel (c) is the exception: it is the twelve channels one at a time, so the metric axis is
    kept and the standardisation is the same arithmetic on the same frozen per-(slot, metric) parameters. That
    the two agree is asserted rather than assumed -- the mean over these twelve values must be the panel
    composite reproduce.py computes -- so this cannot quietly become a second definition of the same number.

    `levels` is the nesting between the root and the panel directories, as in cells(): one for a tree with a
    directory per paper, none for a tree that holds its panel directories at the root.
    """
    out: dict[str, dict[str, dict[str, list]]] = {}
    for f, r in load("/".join([root] + ["*"] * levels + ["panel*", pat])).items():
        parts = f.split("/")
        slot, panel = os.path.basename(f)[:2], parts[-2]
        unit = "/".join(parts[-(levels + 2):-2]) if levels else "."
        for m in metrics:
            key = f"{slot}|{m}"
            if m in r.get("metrics", {}) and sd.get(key):
                out.setdefault(unit, {}).setdefault(panel, {}).setdefault(m, []).append(
                    (r["metrics"][m]["score"] - mu[key]) / sd[key])
    return {u: {p: {m: st.mean(v) for m, v in d.items()} for p, d in pd.items()} for u, pd in out.items()}


def check_rows(fig, rows, gap_pt=0.8, edge_pt=0.5, leading=1.15):
    """Panel (c)'s names and counts sit in their gutters, and its rows are far enough apart to read.

    The two failure modes of a twelve-row strip are both invisible on a whole-figure look. A channel name is as
    long as the rubric happens to make it -- "overall recommendation" is a fifth of the figure's width at this
    size -- so a name grows leftward off the canvas or rightward over the data it labels, and the count on the
    other side does the same. Those are measured here from the renderer, against each strip's own edges.

    The other is crowding: six rows in a panel of a given height fix the leading, and nothing else in this file
    would notice a pitch below the type size. That one is checked from the geometry rather than the renderer,
    because a Text extent is the line box and includes leading the glyphs do not fill, so measuring ink would
    pass a pitch that reads as one solid block.
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    px = fig.dpi / 72.0
    W = fig.get_size_inches()[0] * fig.dpi
    bad = []
    for name, count, ax in rows:
        ab = ax.get_window_extent(r)
        nb, cb = Text.get_window_extent(name, r), Text.get_window_extent(count, r)
        if nb.x1 > ab.x0 - gap_pt * px:
            bad.append(f"{name.get_text()!r} reaches {(nb.x1 - ab.x0) / px:+.1f}pt of its own strip's left edge")
        if nb.x0 < edge_pt * px:
            bad.append(f"{name.get_text()!r} starts {(edge_pt * px - nb.x0) / px:.1f}pt off the canvas")
        if cb.x0 < ab.x1 + gap_pt * px:
            bad.append(f"the count {count.get_text()!r} is {(ab.x1 - cb.x0) / px:+.1f}pt inside the strip")
        if cb.x1 > W - edge_pt * px:
            bad.append(f"the count {count.get_text()!r} runs {(cb.x1 - W) / px:+.1f}pt past the canvas")
    for ax in {id(row[2]): row[2] for row in rows}.values():
        n = len({round(t.get_position()[1], 6) for t, _, a in rows if a is ax})
        h = ax.get_window_extent(r).height / px
        if h / max(n, 1) < leading * PT_FINE:
            bad.append(f"{n} rows in {h:.1f}pt of strip is {h / max(n, 1):.1f}pt a row, under "
                       f"{leading:.2f} times the {PT_FINE} pt type")
    assert not bad, "panel (c)'s rows do not fit:\n  " + "\n  ".join(bad)


def main():
    os.makedirs(OUT, exist_ok=True)
    calib = json.load(open(f"{B}/calibration/calibration_params_portable.json"))
    mu, sd, metrics = calib["mu"], calib["sd"], calib["metrics"]

    # The reference field, recomputed the way every expectation row recomputes it.
    acc = composites(f"{B}/reviews/accepted", mu, sd, metrics)
    field = {p: st.mean(d.values()) for p, d in acc.items()}
    ref = calib["per_paper_composite"]
    worst = max(abs(field[p] - ref[p]) for p in ref)
    assert worst < 1e-4, f"the composite here is not the calibration file's composite ({worst:.2e})"
    fmed, fmax = st.median(field.values()), max(field.values())

    # The instrument's own resolution: two panels on byte-identical text, and the gap between neighbours.
    steps = sorted(abs(d["panel1"] - d["panel2"]) for d in acc.values() if len(d) == 2)
    band, band90 = st.median(steps), steps[int(0.9 * (len(steps) - 1))]
    order = sorted(field.values())
    adjacent = st.median([b - a for a, b in zip(order, order[1:])])

    # The declined papers, and the one of them this figure reads through.
    dec = list(json.load(open(f"{B}/data/analysis_results.json"))["papers"])
    dec_z = [p["composite"] for p in dec]
    clears = sum(1 for x in dec_z if x > fmed)
    # Which declined paper gets the diamond is settled by the instrument rather than by hand: it is the one
    # the panel puts highest. So the choice is recomputable from the bundle, and it cannot be a paper picked
    # for how well it makes the point. Its twelve channels are read here rather than its composite, because
    # (c) needs the channels and a second path to the same number is a second chance to disagree with it --
    # the assertion below is what makes the two paths one.
    ch_rej = channels(f"{B}/reviews/rejected", mu, sd, metrics)
    rej_z = {p: st.mean(st.mean(d.values()) for d in pd.values()) for p, pd in ch_rej.items()}
    focal = max(rej_z, key=lambda p: rej_z[p])
    foc = rej_z[focal]
    assert abs(foc - max(dec_z)) < 1e-9, f"{focal} is not the highest composite of the declined set"
    margin = foc - fmax
    n_field, n_dec = len(field), len(dec_z)

    # The same readout, one rated quality at a time: panel (c). The composite is a mean of these twelve, so a
    # reader who is shown only the composite is shown one twelfth of what the instrument returns, and the
    # positions differ enough between channels that the composite hides them: the paper drawn here is over
    # the whole accepted field on one channel and in the bottom quarter of it on another.
    ch_acc = channels(f"{B}/reviews/accepted", mu, sd, metrics)
    worst = max(abs(st.mean(d.values()) - acc[p][pan]) for p, pd in ch_acc.items() for pan, d in pd.items())
    assert worst < 1e-9, f"the twelve channels here do not average to reproduce.py's composite ({worst:.2e})"
    ch_field = {m: sorted(st.mean(pd[pan][m] for pan in pd) for pd in ch_acc.values()) for m in metrics}
    # Each channel's own re-run band, by the estimator the composite's band uses one paragraph above: two
    # panels over byte-identical text, median absolute difference over the sixteen papers. Every one of the
    # twelve is wider than the composite's, which is the reason the marker in (c) carries its own bar rather
    # than the one in (b): a channel is read off a twelfth of the evidence and moves further on a re-run.
    ch_band = {m: st.median(sorted(abs(list(pd.values())[0][m] - list(pd.values())[1][m])
                                   for pd in ch_acc.values() if len(pd) == 2)) for m in metrics}
    assert min(ch_band.values()) > band, "a channel's re-run band is narrower than the composite's"
    ch_foc = {m: st.mean(pd[m] for pd in ch_rej[focal].values()) for m in metrics}
    assert abs(st.mean(ch_foc.values()) - foc) < 1e-9, "(c)'s channels do not average to (b)'s marker"
    ch_over = {m: sum(1 for v in ch_field[m] if ch_foc[m] > v) for m in metrics}

    # --- the vertical layout, in inches from the top of the canvas ------------------------------------
    # Fractions were enough for two panels of fixed height. There are three now, and panel (a)'s height is
    # set by its own content -- one line added to one box changes it -- so every fraction in a hand-placed
    # layout would have to be recomputed by hand whenever a line was added, and the leading of the run flow
    # would change with it. Inches, then, and the fractions are derived at the bottom of this block.
    FIG_W = 5.5
    TOP = 0.985            # the run flow hangs from just under (a)'s top edge
    box_in = max(stage_height_in(lines) for *_, lines in STAGES)
    GEOM["h_a"] = box_in / TOP
    H_B, H_C = 0.795, 0.680                 # (b)'s three strips; (c)'s six rows, twice over
    TITLE_IN, FOOT_B, FOOT_C = 0.040, 0.370, 0.400   # a title's baseline to its axes; the two axis labels
    GAP_AB, GAP_BC = 0.272, 0.100           # (a)'s roster note hangs in the first of these
    NOTE_C = 0.240                          # (c)'s two fine lines, between its title and its strips
    y = 0.159                               # the canvas top to (a)'s top edge: (a)'s title sits in it
    a_top = y
    b_title = y + GEOM["h_a"] + GAP_AB
    b_top = b_title + TITLE_IN
    c_title = b_top + H_B + FOOT_B + GAP_BC
    c_top = c_title + NOTE_C
    FIG_H = c_top + H_C + FOOT_C

    def yf(inches_from_top):
        return 1.0 - inches_from_top / FIG_H

    fig = plt.figure(figsize=(FIG_W, FIG_H))
    # Placed by hand rather than by a gridspec, because the panels want different left edges: (a) uses the
    # full text width for four columns of run flow, and (b) and (c) need a gutter outside their axes wide
    # enough to name each row beside the row itself. A shared left margin gives one of them the wrong one, and
    # a row label written inside the axes is what produced the collisions check_clear now catches.
    LEFT = 0.010          # the shared left edge: panel (a)'s boxes, every panel title, nothing to its left
    axA = fig.add_axes([LEFT, yf(a_top + GEOM["h_a"]), 0.985, GEOM["h_a"] / FIG_H])
    B_X0, B_W = 0.200, 0.795   # (b)'s strip: the gutter to its left is where its row names go, and (c)
    axB = fig.add_axes([B_X0, yf(b_top + H_B), B_W, H_B / FIG_H])

    # Both titles are figure text at one x. A panel title set on its own axes starts at that axes' left edge,
    # and (b) is inset by the width of its gutter, so the two would step in by a third of an inch against
    # each other -- a misalignment no check in the repository can see and every reader can.
    def title(inches_from_top, text):
        return fig.text(LEFT, yf(inches_from_top), text, fontsize=PT_TITLE, fontweight="bold", ha="left",
                        va="bottom", color=INK)

    # ---- (a) how the panel is built and how a paper becomes a number --------------------------------
    axA.axis("off")
    title(a_top - 0.029, "a  the review instrument, end to end")
    box_h = max(stage_height(lines) for *_, lines in STAGES)
    assert abs(box_h - TOP) < 1e-9, "the panel was not sized to its own tallest box"
    for x0, x1, header, lines in STAGES:
        stage(axA, x0, x1, header, lines, box_h)
    mid = TOP - box_h / 2
    for x0, x1 in ((0.2285, 0.2545), (0.4870, 0.5130), (0.7455, 0.7715)):
        arrow(axA, x0, x1, mid)
    # What the two rosters of box 3 are for, stated once and below the flow, so it does not read as a fifth
    # stage. Positioned against the bottom of the boxes rather than a constant, so it cannot drift under them.
    # The corpus total belongs on this line rather than in a box: it is a property of the whole study, not of
    # one stage, and read out of the scope file rather than typed, so a rescore that changes the count changes
    # the figure. The line is measured against the panel below, since it is the widest thing under the flow.
    n_rev = json.load(open(f"{B}/data/sample_scope.json"))["reviews_total"] \
        if os.path.exists(f"{B}/data/sample_scope.json") else \
        json.load(open(f"{HERE}/sample_scope.json"))["reviews_total"]
    strip = axA.text(0.000, TOP - box_h - frac(0.050),
                     "every result is computed on roster A and repeated on roster B, each reading a "
                     f"checksum-identical prompt; {n_rev:,} reviews in all",
                     transform=axA.transAxes, ha="left", va="top", fontsize=PT_FINE, color=MUTE, zorder=3)

    # ---- (b) the readout: where one paper sits in the field the scale is built on -------------------
    # The title names the box the marker comes out of. Nothing in the earlier version did: a reader met a
    # distribution under four boxes and had to work out for themselves what it had to do with them. Saying it
    # in the title costs no line of prose, and the shared colour on box 4's last line and on this panel's own
    # marker is the same statement made a second way, for a reader who is looking rather than reading.
    title(b_title, "b  the composite from step 4, against the field it is scored in")
    Y_FIELD, Y_DEC, Y_FOC = 2.0, 1.0, 0.0
    fvals = sorted(field.values())
    # Both limits are taken over everything drawn, including the focal paper's band. Written as the focal
    # composite plus a margin it was an upper limit that happened to clear the field, and the field's highest
    # paper fell off the right-hand end the moment the diamond moved down into the distribution.
    lo, hi = min(fvals + dec_z) - 0.28, max(fvals + dec_z + [foc + band]) + 0.34
    SPAN = "#dfe6ec"   # the published range, as a tint rather than a rule, so it reads as an extent

    # Drawn to the rows rather than to the panel. As a full-height span it ran under both notes, so each of
    # them straddled the tint's vertical edge and sat half on it and half on paper: the target's note read as
    # something inside the accepted range, which is the one thing this panel exists to say it is not. Bounded
    # in data coordinates on both axes so it stays put when a number moves the limits.
    SPAN_LO, SPAN_HI = Y_FOC - 0.30, Y_FIELD + 0.35
    axB.add_patch(Rectangle((fvals[0], SPAN_LO), fmax - fvals[0], SPAN_HI - SPAN_LO,
                            facecolor=SPAN, edgecolor="none", zorder=0))
    # The threshold stops short of the target's row: it is a statement about the two populations, and a rule
    # carried all the way down would strike through the note that sits under the target marker.
    axB.vlines(fmed, Y_FOC + 0.55, Y_FIELD + 0.38, color=RULE, lw=0.7, ls=(0, (3.5, 2.2)), zorder=1)

    axB.scatter(fvals, [Y_FIELD] * n_field, s=15, c=ACC, marker="o",
                linewidths=0.4, edgecolors="white", zorder=3)
    axB.scatter(dec_z, [Y_DEC] * n_dec, s=15, c=REJ, marker="^",
                linewidths=0.4, edgecolors="white", zorder=3)
    # The target paper, with the instrument's own re-run band as its error bar.
    axB.errorbar([foc], [Y_FOC], xerr=[[band], [band]], fmt="D", ms=4.2, mfc=FOC,
                 mec="white", mew=0.5, ecolor=FOC, elinewidth=1.0, capsize=1.8,
                 capthick=0.8, zorder=4)

    # Each strip is named in the gutter, level with the strip, so no reader has to work out which label goes
    # with which row and no label is drawn over a paper. x is in axes fractions and y in data, which is what
    # keeps the labels outside the plotting area however the limits move.
    gut = axB.get_yaxis_transform()
    labels = [axB.text(-0.014, y, t, transform=gut, ha="right", va="center",
                       fontsize=PT_ANN, color=c, zorder=5)
              for y, t, c in ((Y_FIELD, f"{n_field} accepted papers", ACC),
                              (Y_DEC, f"{n_dec} declined papers", REJ_TXT),
                              (Y_FOC, f"the highest of the {n_dec}", FOC))]
    # A row is one unit apart from the next and a line of type at this size needs more than that once the
    # markers have taken their share, so nothing can be written between the strips. Everything goes above the
    # top row, below the bottom one, or in the gutter. The threshold note is therefore one line above the
    # accepted strip, run to the right-hand end of the axis for width; the dashed rule stops just under it,
    # so the note reads as the rule's own label without being centred on it.
    # The note runs to the right-hand end of the axis for width, and then backs off it by a fixed few points.
    # The offset is in points rather than in data units because the axis limits move with the numbers and a
    # margin expressed as a fraction of them is a margin that quietly disappears.
    inset = offset_copy(axB.transData, fig=fig, x=-5.0, y=0.0, units="points")
    notes = [
        # The tint is named here, in the note that already describes the field, because it had no name at all:
        # a reader met a grey rectangle spanning most of the panel and nothing said what its edges were. That is
        # the same defect as leaving the panel's composition to prose -- an internal convention presented as if
        # it were shared -- and it is worse in the opening figure than anywhere else. It also disambiguates the
        # target's note, since an unnamed rectangle beside the words "inside the bar" is a second candidate for
        # what "the bar" means. One line, so "declined papers" gives up its noun to the row label that supplies
        # it; the assertion below is what keeps the sentence inside the panel as the numbers move.
        axB.text(hi, Y_FIELD + 0.42, f"shaded: the accepted range. field median, {sgn(fmed, 3)} z: "
                                     f"{clears} of the {n_dec} declined are above it",
                 ha="right", va="bottom", fontsize=PT_FINE, color=MUTE, zorder=5, transform=inset),
        # A count of the papers this one outscores, not a place in the field and not a margin against its top.
        # The count is the statement the instrument supports: it survives a re-run of either paper, while "above
        # every one of the 16" and "under the highest by 0.209" are both readings of a single build that the band
        # on the same marker is wide enough to move. The band is named on the second line for that reason -- the
        # figure gives the number and its resolution together, in the one place a reader meets them both.
        # Under the marker it is about, right-aligned to the same end of the axis as the note above it, and
        # with no leader. The leader it used to have ran from the note up to the error bar's left cap, in the
        # bar's own colour and weight and along the bar's own axis, so the two joined into a single horizontal
        # line and the drawn interval looked several times its width. A reader who mis-measures the bar
        # mis-reads the whole panel. Proximity and colour carry the association instead.
        axB.text(hi, Y_FOC - 1.05,
                 f"{sgn(foc, 3)} z, over {sum(1 for v in fvals if foc > v)} of the {n_field} accepted "
                 f"papers\n"
                 f"the bar is {band:.3f}, what the panel moves by on identical text",
                 transform=inset, ha="right", va="center", fontsize=PT_FINE, color=FOC, zorder=5,
                 linespacing=1.25),
    ]

    axB.set_xlim(lo, hi)
    # The lower limit is set by the target's note, which now sits under the bottom row instead of across it.
    # In the earlier version the note was centred just below the row inside a panel too short to hold it, so
    # its second line ran into the axis spine and the block read as a fourth strip of data.
    axB.set_ylim(-1.85, 2.95)
    axB.set_yticks([])
    axB.set_xlabel("composite, in standard deviations of the accepted set", fontsize=PT_LAB)
    axB.tick_params(labelsize=PT_TICK)
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)

    # ---- (c) the same readout, one rated quality at a time ------------------------------------------
    # The composite of (b) is a mean of twelve, and the instrument returns all twelve. Shown only the mean, a
    # reader sees one number where there are twelve independent readings, and the twelve do not agree: the
    # declined paper drawn here sits low in the field on reproducibility and figure quality and over the whole
    # of it on calibration honesty. That spread is the thing the composite averages away, and it is what an
    # author actually gets back -- a profile with places to look, not a grade.
    #
    # Every row is drawn in (b)'s marks: the accepted papers as the same blue circles, their range as the same
    # tint, the focal paper as the same diamond with the same bar. So the panel needs no legend of its own
    # beyond two lines saying which quantity each mark is, and a reader who has read (b) can read (c) at once.
    # The bar is per channel, not (b)'s: each channel is read off a twelfth of the evidence and moves further
    # on a re-run than the composite does, which is asserted above rather than described here.
    title(c_title, "c  the twelve rated qualities behind that composite, each against the same field")
    notes_c = [fig.text(LEFT, yf(c_title + 0.105 * i), t, fontsize=PT_FINE, color=MUTE, ha="left",
                        va="bottom")
               for i, t in ((1, "one row per quality, as in (b): shaded, the range of the 16 accepted "
                                "papers; grey tick, their median."),
                            (2, "at the right, how many of the 16 the declined paper is above; each bar is "
                                "that quality's own re-run band."))]
    # The name, the strip and the count, in inches, and the block is fitted to (b)'s rather than given its
    # own margins: a name in (c) begins where a name in (b) begins and the second column's count ends where
    # (b)'s strip ends, so the two readouts read as one exhibit. Chosen by hand they were a few points out of
    # step, which is the misalignment nothing in this file can see and every reader can. The gutter has to hold
    # the longest name the rubric produces -- "overall recommendation" -- and check_rows measures all three.
    RIGHT_C = 0.28
    GUT_C = (B_X0 - LEFT) * FIG_W
    W_C = ((B_W * FIG_W) - GUT_C - 2 * RIGHT_C) / 2
    x_c = [LEFT * FIG_W, LEFT * FIG_W + GUT_C + W_C + RIGHT_C]
    axC = [fig.add_axes([(x + GUT_C) / FIG_W, yf(c_top + H_C), W_C / FIG_W, H_C / FIG_H]) for x in x_c]
    # Ordered by where the focal paper falls, which is the panel's subject, so the columns read as one list
    # from the weakest channel to the strongest instead of in the order the schema happens to declare.
    order_c = sorted(metrics, key=lambda m: ch_foc[m])
    lo_c = min(min(ch_field[m] + [ch_foc[m] - ch_band[m]]) for m in metrics) - 0.22
    hi_c = max(max(ch_field[m] + [ch_foc[m] + ch_band[m]]) for m in metrics) + 0.22
    rows_c = []
    for ax, col in zip(axC, (order_c[:6], order_c[6:])):
        for i, m in enumerate(col):
            y = len(col) - 1 - i
            f = ch_field[m]
            ax.add_patch(Rectangle((f[0], y - 0.21), f[-1] - f[0], 0.42,
                                   facecolor=SPAN, edgecolor="none", zorder=0))
            # Over the dots, not under them. Underneath it was invisible on half the rows -- sixteen
            # markers on a strip this narrow leave few gaps, and the median of a distribution tends to land
            # where the distribution is densest -- so the one summary the row carries was hidden by the data
            # it summarises. Taller than the marker row for the same reason.
            ax.vlines(st.median(f), y - 0.34, y + 0.34, color=TICK_C, lw=1.0, zorder=3.5)
            ax.scatter(f, [y] * len(f), s=4.5, c=ACC, marker="o", linewidths=0.25,
                       edgecolors="white", zorder=3)
            ax.errorbar([ch_foc[m]], [y], xerr=[[ch_band[m]], [ch_band[m]]], fmt="D", ms=3.2, mfc=FOC,
                        mec="white", mew=0.4, ecolor=FOC, elinewidth=0.9, capsize=1.4, capthick=0.7,
                        zorder=4)
            g = ax.get_yaxis_transform()
            rows_c.append((ax.text(-0.022, y, m.replace("_", " "), transform=g, ha="right", va="center",
                                   fontsize=PT_FINE, color=INK, zorder=5),
                           ax.text(1.022, y, f"{ch_over[m]}/{n_field}", transform=g, ha="left", va="center",
                                   fontsize=PT_FINE, color=MUTE, zorder=5),
                           ax))
        ax.set_xlim(lo_c, hi_c)
        ax.set_ylim(-0.7, len(col) - 0.3)
        ax.set_yticks([])
        ax.set_xticks([t for t in range(-2, 4) if lo_c < t < hi_c])
        ax.tick_params(labelsize=PT_TICK)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
    # One axis label for both strips, centred between them, because the two columns are one scale split in
    # half rather than two plots: a label under each would read as two different quantities.
    fig.text(sum(x + GUT_C + W_C / 2 for x in x_c) / (2 * FIG_W), yf(c_top + H_C + 0.300),
             "the quality's score, in standard deviations of the accepted set", fontsize=PT_LAB,
             ha="center", va="bottom", color=INK)

    check_fit(fig, axA)
    check_frames(fig)
    check_clear(fig, axB, labels + notes,
                [(fvals, Y_FIELD, 4.4, "an accepted paper"),
                 (dec_z, Y_DEC, 4.4, "a declined paper"),
                 ([foc - band, foc, foc + band], Y_FOC, 4.6, "the target paper or its band")])
    check_span(fig, axB, notes)
    # (c)'s labels are a regular grid rather than hand-placed notes, so the pair-wise part of check_clear is
    # not what to ask of them: at this pitch two consecutive line boxes touch while their glyphs do not, and
    # the crowding question is answered by the leading floor in check_rows instead. What matters here is the
    # same thing (b) was failing silently -- a label drawn over the data it names -- so each column is checked
    # against its own markers, and every name and count against its own gutter.
    for ax, col in zip(axC, (order_c[:6], order_c[6:])):
        marks = []
        for i, m in enumerate(col):
            y = len(col) - 1 - i
            marks.append((ch_field[m], y, 2.1, f"an accepted paper's {m.replace('_', ' ')}"))
            marks.append(([ch_foc[m] - ch_band[m], ch_foc[m], ch_foc[m] + ch_band[m]], y, 3.4,
                          f"the focal paper's {m.replace('_', ' ')} or its band"))
        check_clear(fig, ax, [t for t, _, a in rows_c if a is ax] + [c for _, c, a in rows_c if a is ax],
                    marks, pad_pt=0.4, pairs=False)
    check_rows(fig, rows_c)
    check_no_overlap(fig)
    check_contrast(fig)
    # The saved width is the placed width, because the build reads each figure's MediaBox and draws it at
    # its own size. Overflowing the text width does not crop, it rescales, so every type size on this figure
    # would come out smaller than the sizes set above -- which is what the first draft of panel (a) did,
    # silently, at 7.75in. Under-running is only a narrow figure, so it warns rather than fails.
    PAD, TEXT_W = 0.02, 5.5
    placed = fig.get_tightbbox(fig.canvas.get_renderer()).width + 2 * PAD
    assert placed <= TEXT_W + 0.01, (f"placed at {placed:.3f}in against a {TEXT_W}in text width, so the "
                                     f"page would rescale every type size here by {TEXT_W / placed:.3f}")
    if placed < TEXT_W - 0.20:
        print(f"  note: {placed:.3f}in wide, {TEXT_W - placed:.2f}in short of the text width")

    fig.savefig(f"{OUT}/F0.pdf", bbox_inches="tight", pad_inches=PAD)
    fig.savefig(f"{OUT}/F0.png", dpi=400, bbox_inches="tight", pad_inches=PAD)
    print(f"wrote {OUT}/F0.pdf and F0.png, placed at {placed:.2f}in wide")
    print(f"(b) field n={n_field} median {sgn(fmed)} max {sgn(fmax)}; declined n={n_dec}, "
          f"{clears} clear the median")
    print(f"    focal {focal} {sgn(foc)}, over {sum(1 for v in field.values() if foc > v)} of {n_field}, "
          f"margin to the top {sgn(margin)}, band {band:.3f}, p90 {band90:.3f}, "
          f"adjacent gap {adjacent:.3f}")
    print(f"(c) {len(metrics)} channels, {GEOM['h_a']:.3f}in of run flow and {FIG_H:.2f}in of figure:")
    for m in order_c:
        f = ch_field[m]
        print(f"    {m.replace('_', ' '):24s} {sgn(ch_foc[m], 3)}  band {ch_band[m]:.3f}  "
              f"field {sgn(f[0], 3)} to {sgn(f[-1], 3)}, median {sgn(st.median(f), 3)}  "
              f"above {ch_over[m]:2d} of {n_field}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

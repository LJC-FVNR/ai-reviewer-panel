#!/usr/bin/env python3
"""Emit appendix E's two per-channel tables from pia_null.json, and check the ones on the page against them.

F4 draws twenty-four per-channel medians and the appendix argues from nine of them, but a reader of the
figure can see which bars are long and cannot read a value off any of them. So the numbers the leak claim
rests on reach the page only as the five the prose happens to name, and the other nineteen are in the
bundle alone. A figure is an exhibit; it does not stand in for the record behind it.

The table is generated rather than typed for the same reason the rest of the chain is: a three-place
rounding of a four-place console line is off by one in the last digit often enough to matter, and a hand
copy of twenty-four values will make that mistake somewhere. A table written out of pia_null.json cannot,
and `--check` fails the build if the page and the bundle drift apart.

The allotted column is the point of the exhibit as much as the deltas are. Which channels each transform
may legitimately move is the single free choice in the whole leak analysis and it is fixed by argument
before any scoring, so the exhibit prints it for all three transforms rather than leaving it to prose.

TWO TABLES, AND WHY THE SECOND ONE EXISTS. The claim-strength transform belongs in the exhibit on two
grounds. It has an allotment of its own -- every channel except figure quality, since an edit that
withdraws a claim and concedes a confound may legitimately reach anything about the argument -- so it can
leak like the other two. And its decomposition carries a finding the composite hides: the composite sits at zero because channels move in opposite directions and cancel. A single
`allotted` column cannot serve both tables, because the two licences are different sets, so the arm gets
its own table with its own licence column rather than a pair of columns that a reader would carry across.

WHICH CONTRAST. Both tables are day-matched: each variant panel is differenced against baseline panels
scored in the same sitting. The cross-sitting roster this exhibit used to print is still in the bundle and
is not printed anywhere, because untouched text reads differently between sittings by more than either
presentation transform moves the composite.

    python3 channel_table.py            # print them
    python3 channel_table.py --write    # regenerate them inside APPENDIX.md
    python3 channel_table.py --check    # fail if the page disagrees with the bundle
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from figstyle import pfmt  # noqa: E402

NULL = os.path.join(HERE, "pia_null.json")
APX = os.path.join(HERE, "APPENDIX.md")

# Each generated block is delimited by its own pair of markers. md2tex.py strips HTML comments, so none of
# this reaches the typeset page; they are here so the build can tell a generated exhibit from a written one.
BLOCKS = {
    "CHANNEL TABLE": None,          # the two presentation transforms, filled in below
    "CONCEDE TABLE": None,          # the claim-strength transform
    "GROUP TABLE": None,            # the two group tests the randomisation test is actually run on
}

# The presentation table's columns: the pooled day-matched five-slot roster, and the second roster of eight
# slots over six vendors. In the order the paper introduces them.
PIA_COLS = [("5model_pooled", "five-slot"), ("8slot", "eight-slot")]
PIA_TRANSFORMS = [("T1_endmatter", "T1"), ("T3_lengthen", "T3")]
# The claim-strength table's columns. One transform, so the columns are readings instead: the pool, the
# corpus the claim was not developed on, and the second roster.
T2_COLS = [("5model_pooled", "both corpora"), ("5model_rejected", "declined only"),
           ("8slot", "eight slots")]
# Group rows are named by size in pia_null.py, and the sizes differ between the two licences, so they are
# matched by prefix rather than by full name.
GROUP_PREFIXES = ["composite", "allotted group", "non-allotted group"]
# The group table's rows: every transform read on every reading the study has, so a reader can see which
# readings a group result replicates in without a sentence choosing which ones to mention. The order is the
# paper's: the claim-strength arm first, because it is the control the other two are read against.
GROUP_READINGS = [("5model_pooled", "five slots, pooled"),
                  ("5model_matched", "five slots, accepted"),
                  ("5model_rejected", "five slots, declined"),
                  ("8slot", "eight slots, accepted")]
GROUP_ORDER = [("T2_concede", "T2 claim strength"), ("T1_endmatter", "T1 end matter"),
               ("T3_lengthen", "T3 sentences joined")]
# Verbatim fig4.SHORT: the table exists to be read down alongside the figure's bars, and two spellings of
# a channel name would break that. "rigor" is the metric's name and stays as the instrument writes it.
NICE = {"significance": "significance", "novelty": "novelty", "rigor": "rigor",
        "statistical_soundness": "statistical soundness", "calibration_honesty": "calibration honesty",
        "clarity": "clarity", "structure_compliance": "structure compliance",
        "reproducibility": "reproducibility", "related_work": "related work",
        "figure_quality": "figure quality", "breadth_generality": "breadth / generality",
        "overall_recommendation": "overall recommendation"}


def fmt(v):
    """-> the value as the appendix writes one: three places, a unicode minus, and no sign on a zero."""
    return "0.000" if f"{v:.3f}" in ("0.000", "-0.000") else f"{v:+.3f}".replace("-", "−")


def axes(d, roster, transform):
    """-> {axis name: (delta, allotted)} for one roster and transform."""
    return {a["axis"]: (a["delta"], a["allotted"])
            for a in d["rosters"][roster]["transforms"][transform]["axes"]}


def group_rows(ax):
    """-> the group axis names present, in GROUP_PREFIXES order."""
    return [next(k for k in ax if k.startswith(pre)) for pre in GROUP_PREFIXES]


def table(d, cols, transforms, rank_on):
    """-> one markdown table: a row per channel, then a row per group axis.

    `cols` is a list of (roster key, header word) and `transforms` a list of (transform key, header word);
    the columns are their product, in that order. `rank_on` names the (roster, transform) whose medians set
    the row order, so the table can be read down alongside the figure's bars rather than searched.
    """
    grid = [(r, t, axes(d, r, t)) for r, _ in cols for t, _ in transforms]
    groups = group_rows(grid[0][2])
    chans = sorted(k for k in grid[0][2] if k not in groups)
    for r, t, ax in grid:
        assert sorted(k for k in ax if k not in group_rows(ax)) == chans, f"{r}/{t} has different channels"
        assert group_rows(ax) == groups, f"{r}/{t} names its group axes differently"

    # One allotted column for several score columns is only honest while the allotment is the same in all
    # of them. It is, within a table: the set is fixed by argument before scoring and does not depend on the
    # roster or the corpus. Across the two tables it is not, which is why there are two tables.
    allot = {c: grid[0][2][c][1] for c in chans}
    for r, t, ax in grid:
        assert {c: ax[c][1] for c in chans} == allot, f"{r}/{t} allots a different set of channels"

    order = sorted(chans, key=lambda c: axes(d, *rank_on)[c][0])
    head = ["channel", "allotted"] + [f"{rn} {tn}" for _, rn in cols for _, tn in transforms]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for c in order:
        cells = [NICE[c], "yes" if allot[c] else ""]
        cells += [fmt(ax[c][0]) for _, _, ax in grid]
        rows.append("| " + " | ".join(cells) + " |")
    for g in groups:
        cells = [f"**{g}**", ""]
        cells += [f"**{fmt(ax[g][0])}**" for _, _, ax in grid]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def group_table(d):
    """-> the licensed and non-licensed group tests, every transform on every reading.

    The randomisation test is run on these two group statistics and on nothing else; the per-channel tables
    above are diagnostics under them. Both p-values are printed because the study's rule is that a group
    counts as moved only where the sign null and the pooled draw agree, and a table that printed one of
    them would let a sentence quote whichever agreed with it.

    The first column was headed "p exact", which is true of the eight- and sixteen-paper rows and false of
    every forty-seven-paper row in this table: past ENUM_MAX papers pia_null.py draws 200,000 sign vectors
    instead of listing 2^47 of them. A reader taking the header at its word would compute the wrong floor for
    two thirds of the rows, so the header now names the construction the two nulls differ in.
    """
    rows = ["| transform | reading | papers | licensed | non-licensed | down/up | p signs "
            "| p pooled |", "|" + "---|" * 8]
    for t, tn in GROUP_ORDER:
        for r, rn in GROUP_READINGS:
            T = d["rosters"].get(r, {}).get("transforms", {}).get(t)
            if not T:
                continue
            ax = {a["axis"]: a for a in T["axes"]}
            al = next(v for k, v in ax.items() if k.startswith("allotted group"))
            na = next(v for k, v in ax.items() if k.startswith("non-allotted group"))
            # Both columns go through the shared spelling, because both of them can hit the floor of
            # their own null, and at four places a floor reads "0.0000" or "< 0.0000". Neither states
            # what happened, which is that no sign assignment out of that many reached the observed
            # value; a p of exactly zero is not a thing a randomisation test can return.
            pe = pfmt(na["p_exact"], na["exact_assignments"])
            pp = pfmt(na["p_pooled"], d["draws"])
            # The column used to be the group's distance from its null in sd of the null. It is now the
            # per-paper sign count, because that distance is not always expressible: the claim-strength arm's
            # non-licensed group is one channel, its re-run differences are exactly zero on a large share of
            # papers, and the median of such a null barely varies -- so the ratio read +28.79 for a group that
            # moved up, printed beside a downward p of 1.0000. The two p columns carry the distance, one of
            # them by enumeration, and a sign count is the scale statement a discrete null cannot distort.
            rows.append(f"| {tn} | {rn} | {na['n_papers']} | {fmt(al['delta'])} | **{fmt(na['delta'])}** "
                        f"| {na['n_negative']}/{na['n_positive']} | {pe} | {pp} |")
    return "\n".join(rows)


def build():
    d = json.load(open(NULL, encoding="utf-8"))
    return {
        "GROUP TABLE": group_table(d),
        "CHANNEL TABLE": table(d, PIA_COLS, PIA_TRANSFORMS, ("5model_pooled", "T3_lengthen")),
        # Ranked on the reading with the most papers behind it, and on the one transform there is.
        "CONCEDE TABLE": table(d, T2_COLS, [("T2_concede", "T2")], ("5model_pooled", "T2_concede")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    # The appendix is the page, but the writing job edits a copy of one of its sections, and that copy
    # carries the same marker pairs. Both have to be fillable from here or the copy gets hand-edited,
    # and a hand-edited generated block is how a table on the page stops matching the analysis it came
    # from without anything noticing.
    ap.add_argument("--into", default=APX, help="the file whose marker pairs to fill (default the appendix)")
    a = ap.parse_args()
    tbls = build()

    if not (a.write or a.check):
        for name, tbl in tbls.items():
            print(f"\n=== {name}\n{tbl}")
        return 0

    apx = open(a.into, encoding="utf-8").read()
    rc = 0
    for name, tbl in tbls.items():
        op = f"<!-- {name}, generated by channel_table.py -->"
        cl = f"<!-- /{name} -->"
        m = re.search(re.escape(op) + r"\n(.*?)\n" + re.escape(cl), apx, re.S)
        if not m:
            print(f"channel_table.py: {os.path.basename(a.into)} has no {name} markers")
            return 2
        if a.check:
            if m.group(1) != tbl:
                print(f"channel_table.py: the {name} on the page is not the one in the bundle")
                want, got = tbl.split("\n"), m.group(1).split("\n")
                for i in range(max(len(want), len(got))):
                    w, g = (want[i] if i < len(want) else ""), (got[i] if i < len(got) else "")
                    if w != g:
                        print(f"  row {i}\n    page   {g}\n    bundle {w}")
                rc = 1
            else:
                print(f"channel_table.py: {name} matches the bundle "
                      f"({len(tbl.splitlines()) - 2} rows)")
        else:
            apx = apx[:m.start(1)] + tbl + apx[m.end(1):]
            print(f"channel_table.py: wrote {len(tbl.splitlines()) - 2} rows of {name}")
    if a.write:
        open(a.into, "w", encoding="utf-8").write(apx)
    return rc


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""What consensus bar does an ICLR-*accepted* paper clear, and does it clear it twice?

§3's claim is that the absolute grade scale carries almost no information. A single modal grade proves
that weakly, because a reader can always answer "you picked the wrong threshold". So report the whole
ladder of plausible bars a venue might set, and let the ladder make the argument: the only bar most
accepted papers clear is the one that admits the near-universal Major Revision.

The second column is the one that matters and it costs nothing extra, because every paper carries two
panels over byte-identical text: a bar that a paper clears in one panel and fails in the other is not a
decision procedure, whatever its pass rate.

An earlier reading of this tree had it that "the all-reviewers-pass bar is cleared by 1 of 16 accepted-paper
panels, and that one paper cleared it in only one of its two panels". That conflates two bars, as this shows: under
the literal all-reviewers reading the count is **0 of 32 panels**, and the "1" belongs to "any single
reviewer says Accept" -- which is indeed cleared by 1 paper in 1 of its 2 panels. Both facts are real and
the ladder states them separately.

Writes consensus_bars.json. Reads the accepted-16 review tree; no reviews are generated.
"""
from __future__ import annotations

import collections
import glob
import json
import os

CAL = "/path/to/workspace/paper_direction_98_calibration"
AN = os.path.dirname(os.path.abspath(__file__))
ORD = {"Reject": 0, "Reject and Resubmit": 1, "Major Revision": 2, "Minor Revision": 3, "Accept": 4}

# Ordered from strictest to most permissive, so the ladder reads top to bottom.
BARS = [
    ("every reviewer at Minor Revision or better", lambda g: all(ORD[x] >= 3 for x in g)),
    ("any single reviewer says Accept", lambda g: any(ORD[x] == 4 for x in g)),
    ("modal grade at Minor Revision or better",
     lambda g: ORD[collections.Counter(g).most_common(1)[0][0]] >= 3),
    ("every reviewer at Major Revision or better", lambda g: all(ORD[x] >= 2 for x in g)),
]


def load():
    """-> {paper: {panel: [5 grades]}}, panels with a missing review dropped."""
    out = {}
    for d in sorted(glob.glob(f"{CAL}/reviews/*")):
        panels = {}
        for p in sorted(glob.glob(f"{d}/panel*")):
            gs = []
            for f in sorted(glob.glob(f"{p}/R*.json")):
                try:
                    g = json.load(open(f)).get("grade")
                except Exception:
                    continue
                if g in ORD:
                    gs.append(g)
            if len(gs) == 5:
                panels[os.path.basename(p)] = gs
        if panels:
            out[os.path.basename(d)] = panels
    return out


def main():
    data = load()
    n_pan = sum(len(v) for v in data.values())
    rows = []
    print(f"{len(data)} accepted ICLR-2026 papers, {n_pan} panels, {n_pan * 5} reviews\n")
    print(f"{'bar':44s} {'panels':>8s} {'papers >=1':>11s} {'papers both':>12s} {'reproduced':>11s}")
    for label, fn in BARS:
        pan = sum(1 for p in data for gs in data[p].values() if fn(gs))
        any_ = [p for p in data if any(fn(gs) for gs in data[p].values())]
        both = [p for p in data if len(data[p]) >= 2 and all(fn(gs) for gs in data[p].values())]
        frac = f"{len(both)}/{len(any_)}" if any_ else "n/a"
        rows.append(dict(bar=label, panels=pan, n_panels=n_pan, papers_any=len(any_),
                         papers_both=len(both), n_papers=len(data), reproduced=frac))
        print(f"{label:44s} {pan:3d}/{n_pan:<4d} {len(any_):6d}/{len(data):<4d} "
              f"{len(both):7d}/{len(data):<4d} {frac:>11s}")

    print("\nThe two sentences this table licenses:")
    strict, accept = rows[0], rows[1]
    modal = rows[2]
    print(f"  1. No panel of any accepted paper has all five reviewers at Minor Revision or better "
          f"({strict['panels']} of {strict['n_panels']}). One paper drew a single Accept, in one of its "
          f"two panels.")
    print(f"  2. Of the {modal['papers_any']} papers whose MODAL grade clears Minor Revision in at least "
          f"one panel, {modal['papers_both']} clears it in both -- so "
          f"{modal['papers_any'] - modal['papers_both']} of {modal['papers_any']} flip on identical text.")

    json.dump({"n_papers": len(data), "n_panels": n_pan, "bars": rows},
              open(f"{AN}/consensus_bars.json", "w"), indent=1)
    print(f"\nwrote {AN}/consensus_bars.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

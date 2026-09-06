#!/usr/bin/env python3
"""Does the pre-registered treatment-strength floor hold over every scored cell, and does the reading depend
on it?

The floor is `pia_transforms.MIN_EDITS`: 3 edits for the relocation arm, 3 for the claim-strength arm, 15 joins
for the sentence-joining arm. The builder records each paper-variant's edit count and lists the cells that fall
under it in the variant tree's own manifest. Two questions follow, and neither is answered anywhere else in this
tree:

  1. Was every below-floor cell actually withheld from the scoring queue? The manifest records an intention;
     `readings.json` records what was scored. Comparing them is the only way to find a cell that was listed and
     read anyway, which is what happened once -- the accepted corpus was scored before the floor existed, so
     its one below-floor relocation variant is in the arm the paper reports.
  2. Does the arm's reading depend on that cell? Asked by recomputing the arm with the floor enforced, on the
     same day-matched roster, the same ruler and the same nulls as `pia_null.py` -- the functions are imported
     from it rather than reimplemented, so the two readings differ in their paper set and in nothing else.

The composite, the two group axes and all twelve channels are recomputed, because the arm's claim is about the
group axes and not about its composite: "this edit stays inside the channels it may move" is a statement about
the nine it may not.

    python3 floor_check.py            # -> floor_check.json
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys

import numpy as np

import pia_null
import pia_transforms

AN = os.path.dirname(os.path.abspath(__file__))
TREES = ("pia_variants", "pia_variants_reject")
ARM = "T1_endmatter"                 # the one arm a below-floor cell reached; asserted below, not assumed
ROSTER = "5model_pooled"             # the reading section 6 reports


def below_floor():
    """-> [(tree, paper, transform, edits, floor)] over both variant trees, from the manifests' own counts.

    Read from `variants` rather than from `excluded`, so a cell missing from the exclusion list because the
    builder was changed after it ran still appears here.
    """
    out = []
    for tree in TREES:
        man = json.load(open(f"{AN}/{tree}/manifest.json"))
        for p in man["papers"]:
            for t, v in man["variants"][p].items():
                if t == "baseline":
                    continue
                floor = pia_transforms.MIN_EDITS[t]
                if v["edits"] < floor:
                    out.append((tree, p, t, v["edits"], floor))
    return out


def scored():
    """-> {(paper, transform)} that carry a reading in the analysed corpus."""
    return {(r["paper"], r["condition"]) for r in json.load(open(f"{AN}/readings.json"))}


def arm(only, transform):
    """-> [row] for the composite, the two group axes and every channel, on one paper set.

    `only` is passed as the roster's paper filter, which `pia_null.axis` applies after both the baseline and
    the variant path have produced their per-paper values, so the same filter reaches the delta and the re-run
    reference the null is scaled from.
    """
    R = dict(pia_null.ROSTERS[ROSTER])
    if only is not None:
        R["only"] = set(only)
    calib = json.load(open(R["params"]))
    mu, sd, metrics = calib["mu"], calib["sd"], calib["metrics"]
    rng = np.random.default_rng(pia_null.SEED)
    allot = sorted(pia_null.LEGIT[transform])
    rest = sorted(set(metrics) - set(allot))
    rows = []
    for name, cols, is_allot in ([("composite (all 12)", metrics, None),
                                  (f"allotted group ({len(allot)})", allot, True),
                                  (f"non-allotted group ({len(rest)})", rest, False)]
                                 + [(m, [m], m in allot) for m in metrics]):
        deltas, rerun, _ = pia_null.axis(cols, R, mu, sd, transforms=(transform,))
        rows.append(pia_null.test(name, len(cols), is_allot, deltas[transform], rerun, rng))
    return rows


def main():
    low = below_floor()
    have = scored()
    read_anyway = [c for c in low if (c[1], c[2]) in have]
    withheld = [c for c in low if (c[1], c[2]) not in have]

    print(f"FLOOR  " + ", ".join(f"{t} {n}" for t, n in sorted(pia_transforms.MIN_EDITS.items())))
    print(f"CELLS  {sum(len(json.load(open(f'{AN}/{x}/manifest.json'))['papers']) for x in TREES)} papers "
          f"x {len(pia_transforms.MIN_EDITS)} transforms")
    for tag, cells in (("WITHHELD", withheld), ("SCORED ANYWAY", read_anyway)):
        print(f"\n{tag} ({len(cells)}):")
        for tree, p, t, e, f in cells:
            print(f"  {tree:20s} {t:14s} {e:3d} edits against a floor of {f}")

    out = {"floor": pia_transforms.MIN_EDITS,
           "below_floor": [dict(tree=x[0], transform=x[2], edits=x[3], floor=x[4]) for x in low],
           "withheld": len(withheld), "scored_anyway": len(read_anyway)}

    if not read_anyway:
        print("\nEvery below-floor cell was withheld; there is no reading to compare.")
        json.dump(out, open(f"{AN}/floor_check.json", "w"), indent=1)
        return 0

    # One arm, one cell: the comparison below is written for that case and would silently report the wrong
    # arm's reading if a second cell were ever scored past the floor.
    assert {c[2] for c in read_anyway} == {ARM}, f"below-floor cells scored on {sorted({c[2] for c in read_anyway})}"
    drop = {c[1] for c in read_anyway}

    # The paper set the floor would have left. Taken as every paper the roster reads MINUS the below-floor
    # ones, rather than as a typed list, because a filter that names its keepers goes stale when the corpus
    # grows and a filter that names its exclusions does not.
    everyone = sorted({p for p, c in have if c == ARM})
    keep = [p for p in everyone if p not in drop]
    assert len(keep) == len(everyone) - len(drop), "the dropped paper is not in the arm being cut"

    print(f"\n{ROSTER} / {ARM}: as reported over {len(everyone)} papers, and with the floor enforced over "
          f"{len(keep)}")
    # Both p-values per axis, both readings. An axis is reported as moved only where the pooled null and the
    # sign null agree, so a flag that changes between the two readings is only worth anything if BOTH p-values
    # moved decisively; one of them stepping over 0.05 while the other sits at 0.049 is the threshold moving,
    # not the result. Printing all four is what lets a reader tell those apart.
    print(f"  {'axis':24s} {'as reported':>12s} {'floor enforced':>15s} {'shift':>9s}  "
          f"{'p pool -> p pool':>17s} {'p sign -> p sign':>17s}  sign")
    both = {}
    for a, b in zip(arm(None, ARM), arm(keep, ARM)):
        assert a["axis"] == b["axis"], f"{a['axis']} against {b['axis']}"
        both[a["axis"]] = {"as_reported": a["delta"], "floor_enforced": b["delta"],
                           "n_as_reported": a["n_papers"], "n_floor_enforced": b["n_papers"],
                           "sign_as_reported": [a["n_negative"], a["n_positive"]],
                           "sign_floor_enforced": [b["n_negative"], b["n_positive"]],
                           "p_pooled_as_reported": a["p_pooled"], "p_pooled_floor_enforced": b["p_pooled"],
                           "p_sign_as_reported": a["p_exact"], "p_sign_floor_enforced": b["p_exact"],
                           "moved_as_reported": a["moved"], "moved_floor_enforced": b["moved"]}
        flag = "" if a["moved"] == b["moved"] else "  <- FLAG CHANGES"
        print(f"  {a['axis']:24s} {a['delta']:+12.4f} {b['delta']:+15.4f} {b['delta'] - a['delta']:+9.4f}  "
              f"{a['p_pooled']:7.4f} ->{b['p_pooled']:8.4f} {(a['p_exact'] or -1):7.4f} ->"
              f"{(b['p_exact'] or -1):8.4f}  "
              f"{a['n_negative']}-/{a['n_positive']}+ -> {b['n_negative']}-/{b['n_positive']}+{flag}")

    out["arm"] = ARM
    out["roster"] = ROSTER
    out["n_as_reported"] = len(everyone)
    out["n_floor_enforced"] = len(keep)
    out["axes"] = both
    out["verdict_unchanged"] = all(v["moved_as_reported"] == v["moved_floor_enforced"]
                                   for v in both.values())
    json.dump(out, open(f"{AN}/floor_check.json", "w"), indent=1)
    print(f"\nevery axis keeps its verdict: {out['verdict_unchanged']}")
    print("wrote floor_check.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

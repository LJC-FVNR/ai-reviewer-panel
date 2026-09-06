#!/usr/bin/env python3
"""§3's grade table, recomputed from the review trees.

The distribution was carried in prose across the drafts ("Major 69% vs 56%", "1 Accept in
480") with no script behind it. Standing rule: every number in the paper is recomputed from the corpus at
write-up. So this counts the grades, and prints the three sentences §3 states.

Four populations of one venue, nested so the wide row sits beside its own restriction:

  accepted 16    the reference field -- papers ICLR 2026 published
  rejected 32    the rejected sample, spanning the widest quality range available
  .. low 16      the lowest-rated half
  .. high 16     the highest-rated half, which is the region a programme committee decides in

The percentages are over REVIEWS, not papers, because the grade is a per-review output; papers carry two
panels of five reviewers, so a 16-paper population is 160 reviews. Accept counts are printed as integers
rather than percentages: at 1 in 480 a percentage reads as a rate when it is one event.

Writes grade_table.json. Reads only; no reviews are generated.
"""
from __future__ import annotations

import glob
import json
import os

AN = os.path.dirname(os.path.abspath(__file__))
CAL = "/path/to/workspace/paper_direction_98_calibration"
GRADES = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]

POPS = [
    ("ICLR accepted 16 (reference field)", sorted(glob.glob(f"{CAL}/reviews/*"))),
    ("ICLR rejected 32 (widest range)", sorted(glob.glob(f"{AN}/reject_arm/reviews/*_*"))),
    (".. low-rated 16 only", sorted(glob.glob(f"{AN}/reject_arm/reviews/low_*"))),
    (".. high-rated 16 only", sorted(glob.glob(f"{AN}/reject_arm/reviews/high_*"))),
]


def count(roots):
    """-> (Counter-as-dict over GRADES, n_reviews, n_papers, n_panels)."""
    c = {g: 0 for g in GRADES}
    n_pap = n_pan = 0
    for d in roots:
        pans = sorted(glob.glob(os.path.join(d, "panel*")))
        seen = 0
        for p in pans:
            hit = 0
            for f in sorted(glob.glob(os.path.join(p, "R*.json"))):
                try:
                    g = json.load(open(f)).get("grade")
                except Exception:
                    continue
                if g in c:
                    c[g] += 1
                    hit += 1
            if hit:
                seen += 1
        if seen:
            n_pap += 1
            n_pan += seen
    return c, sum(c.values()), n_pap, n_pan


def main():
    out, total_n, total_acc = {}, 0, 0
    hdr = f"{'population':36s} {'reviews':>7s} " + " ".join(f"{g[:9]:>9s}" for g in GRADES)
    print(hdr)
    for label, roots in POPS:
        c, n, npap, npan = count(roots)
        if not n:
            continue
        # The two nested halves are inside the 32, so only top-level rows join the corpus total.
        if not label.startswith(".."):
            total_n += n
            total_acc += c["Accept"]
        row = {"n_reviews": n, "n_papers": npap, "n_panels": npan, "counts": c,
               "pct": {g: round(100.0 * c[g] / n, 1) for g in GRADES}}
        out[label] = row
        print(f"{label:36s} {n:7d} " + " ".join(f"{c[g]:4d} {row['pct'][g]:4.0f}%" for g in GRADES))

    print(f"\ncorpus total (accepted 16 + rejected 32, no double counting): {total_n} reviews, "
          f"{total_acc} Accept ({100.0 * total_acc / total_n:.2f}%)")
    out["_total"] = {"n_reviews": total_n, "n_accept": total_acc,
                     "accept_pct": round(100.0 * total_acc / total_n, 4)}

    acc, hi = out["ICLR accepted 16 (reference field)"], out[".. high-rated 16 only"]
    rej = out["ICLR rejected 32 (widest range)"]
    print("\nThe three sentences §3 states:")
    print(f"  1. It will not say Accept ({acc['counts']['Accept']} in {acc['n_reviews']} reviews of "
          f"published papers) and it will not say Reject "
          f"({rej['pct']['Reject']:.0f}% on rejected ones).")
    print(f"  2. Major Revision is modal on both sides of the venue's boundary, and identical at the top: "
          f"{acc['counts']['Major Revision']}/{acc['n_reviews']} accepted vs "
          f"{hi['counts']['Major Revision']}/{hi['n_reviews']} high-rated rejected.")
    lad = [out[k]['counts']['Reject and Resubmit'] for k in
           ["ICLR accepted 16 (reference field)", ".. high-rated 16 only", ".. low-rated 16 only"]]
    mono = all(a < b for a, b in zip(lad, lad[1:]))
    print(f"  3. Reject-and-Resubmit does ladder: {' / '.join(str(x) for x in lad)} across accepted, "
          f"high-rated rejected, low-rated rejected{' (monotone)' if mono else ' (NOT monotone -- check)'}"
          f" -- the grade separates the bottom of the pile, not the decision region.")

    if acc['counts']['Major Revision'] != hi['counts']['Major Revision']:
        print("\nNOTE: the two Major Revision counts are no longer equal. §3 calls them identical; "
              "restate as 'nearly identical' with both counts, or find what changed in the trees.")

    json.dump(out, open(f"{AN}/grade_table.json", "w"), indent=1)
    print(f"\nwrote {AN}/grade_table.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

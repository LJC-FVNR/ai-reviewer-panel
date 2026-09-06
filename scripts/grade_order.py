#!/usr/bin/env python3
"""The grade axis read as an order, beside the composite it is usually contrasted with.

Section 3 shows what the grade cannot do: the modal grade is the same on both sides of the venue's own
decision, the top grade is awarded once in 480 reviews, and the level moves when the roster does. None of
that is a statement about the grade's ORDER. A reader with this bundle can average the five-level grade over
a paper's ten reviews and correlate it with the venue's rating, and the paper has to say what that returns
before someone else does.

Three readings of the same reviews, each a paper-level number:

    composite    the mean channel z over the paper's reviews, which is the instrument as the paper defines it
    grade mean   the five grades coded 0-4 and averaged, an equal-interval reading of an ordinal ladder
    bar share    the share of the paper's reviews at Minor Revision or better, which is the prompt's own
                 mapping to an ICLR 6 -- at or above the acceptance bar -- and so needs no interval assumption

Each is scored against the same two criteria the paper already uses: the venue's post-rebuttal mean rating
over the 32 declined papers, and the accepted-against-declined separation over all 48. The difference between
two correlations on one set of papers is a paired quantity, so its interval resamples papers once and applies
the same draw to both readings; an unpaired interval around a difference of correlations is an interval around
the wrong statistic.

The point of the comparison is what it costs the paper's own instrument: if a coarse ordinal ladder orders
these papers as well as twelve calibrated channels, the composite's contribution is the calibration -- an
absolute reference population, which the grade has none of -- rather than resolution.

    python3 grade_order.py [--bundle release/aina2026_agent_reviewers] [--out grade_order.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import statistics as st

LADDER = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]
BAR = LADDER.index("Minor Revision")     # the prompt maps this grade to an ICLR 6, above the acceptance bar


def ranks(v):
    """Ranks with ties averaged, which the venue ratings need: eleven low-arm papers share one rating."""
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs, ys):
    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def auc(pos, neg):
    return sum(1 if a > b else 0.5 if a == b else 0 for a in pos for b in neg) / (len(pos) * len(neg))


def paired_ci(fn, *cols, seed=20260905, draws=20000):
    """Percentile interval for a statistic of several aligned columns, resampling papers once per draw.

    Non-finite draws are dropped rather than sorted. The bar share takes five distinct values over these 32
    papers and is zero for 24 of them, so a resample can draw 32 papers that all sit at zero; a correlation
    with a constant column is undefined, and a NaN in the list makes the sort meaningless -- the symptom is a
    percentile interval that moves by 0.16 with the seed, and once an upper bound below its own lower bound.
    Dropped draws are counted and the count is returned, because a silently censored bootstrap is an interval
    over a population the reader was not told about.
    """
    rng = random.Random(seed)
    out, dropped = [], 0
    for _ in range(draws):
        idx = [rng.randrange(len(cols[0])) for _ in cols[0]]
        try:
            value = fn(*[[c[i] for i in idx] for c in cols])
        except (ZeroDivisionError, ValueError):
            value = float("nan")
        if value == value and abs(value) != float("inf"):
            out.append(value)
        else:
            dropped += 1
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))], dropped


def readings(bundle, corpus, pattern="R?.json", calibration=None):
    """-> {paper: {grade_mean, bar_share, composite, reviews}} over one corpus of the released tree."""
    out: dict[str, dict] = {}
    for path in sorted(glob.glob(f"{bundle}/reviews/{corpus}/*/panel*/{pattern}")):
        paper = path.split(os.sep)[-3]
        slot = os.path.basename(path).split(".")[0]
        review = json.load(open(path, encoding="utf-8"))
        row = out.setdefault(paper, {"grades": [], "z": []})
        row["grades"].append(LADDER.index(review["grade"]))
        if calibration:
            for metric in calibration["metrics"]:
                key = f"{slot}|{metric}"
                row["z"].append((review["metrics"][metric]["score"] - calibration["mu"][key])
                                / calibration["sd"][key])
    return {p: {"reviews": len(r["grades"]),
                "grade_mean": st.mean(r["grades"]),
                "bar_share": st.mean(g >= BAR for g in r["grades"]),
                "composite": st.mean(r["z"]) if r["z"] else None,
                "at_bar": sum(1 for g in r["grades"] if g >= BAR),
                "top": sum(1 for g in r["grades"] if g == len(LADDER) - 1)}
            for p, r in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="release/aina2026_agent_reviewers")
    ap.add_argument("--out", default="grade_order.json")
    a = ap.parse_args()

    cal = json.load(open(f"{a.bundle}/calibration/calibration_params_portable.json", encoding="utf-8"))
    accepted = readings(a.bundle, "accepted", calibration=cal)
    declined = readings(a.bundle, "rejected", calibration=cal)
    vendor = readings(a.bundle, "vendor_panel", pattern="C?.json")
    ratings = json.load(open(f"{a.bundle}/data/rejected_arm_ratings.json", encoding="utf-8"))["papers"]

    keys = sorted(declined)
    human = [ratings[k]["rating_mean"] for k in keys]
    cols = {name: [declined[k][name] for k in keys] for name in ("composite", "grade_mean", "bar_share")}
    arm = {side: [i for i, k in enumerate(keys) if ratings[k]["arm"] == side] for side in ("high", "low")}

    # Each reading's own coefficient with an interval, which is what the aggregation panel draws: the five
    # single slots and the panel are already on that axis, and these two rows put the grade beside them.
    rho = {name: spearman(col, human) for name, col in cols.items()}
    rho_ci = {}
    for name, col in cols.items():
        low, high, dropped = paired_ci(spearman, col, human)
        rho_ci[name] = {"low": low, "high": high, "undefined_draws": dropped}
    separation = {name: auc([accepted[k][name] for k in accepted], [declined[k][name] for k in declined])
                  for name in cols}
    within = {name: auc([col[i] for i in arm["high"]], [col[i] for i in arm["low"]])
              for name, col in cols.items()}

    def gap(a_col, b_col, criterion):
        return spearman(a_col, criterion) - spearman(b_col, criterion)

    def difference(name):
        low, high, dropped = paired_ci(gap, cols[name], cols["composite"], human)
        return {"point": gap(cols[name], cols["composite"], human),
                "ci": [low, high], "undefined_draws": dropped}

    # The two rosters on the sixteen papers both read. The composite's cross-roster agreement is appendix H's
    # +0.971; these are the same comparison for the grade, which is the reading that has no calibration to
    # carry an order across a roster change.
    both = sorted(set(vendor) & set(accepted))
    across = {name: spearman([accepted[k][name] for k in both], [vendor[k][name] for k in both])
              for name in ("grade_mean", "bar_share")}

    result = {
        "unit": "paper; the mean over its reviews of a per-review reading",
        "ladder": dict(zip(LADDER, range(len(LADDER)))),
        "bar": "Minor Revision or better, which the prompt maps to an ICLR rating of 6",
        "reviews": {"accepted": sum(v["reviews"] for v in accepted.values()),
                    "declined": sum(v["reviews"] for v in declined.values()),
                    "vendor_panel": sum(v["reviews"] for v in vendor.values())},
        "at_bar": {"accepted": sum(v["at_bar"] for v in accepted.values()),
                   "declined": sum(v["at_bar"] for v in declined.values()),
                   "vendor_panel": sum(v["at_bar"] for v in vendor.values())},
        "top_grade": {"accepted": sum(v["top"] for v in accepted.values()),
                      "declined": sum(v["top"] for v in declined.values()),
                      "vendor_panel": sum(v["top"] for v in vendor.values())},
        "bar_share_mean": {"accepted": st.mean(v["bar_share"] for v in accepted.values()),
                           "declined": st.mean(v["bar_share"] for v in declined.values()),
                           "vendor_panel": st.mean(v["bar_share"] for v in vendor.values())},
        "rho_vs_venue_rating": rho,
        "rho_vs_venue_rating_ci": rho_ci,
        "rho_gap_grade_minus_composite": difference("grade_mean"),
        "rho_gap_bar_share_minus_composite": difference("bar_share"),
        "auc_high_vs_low": within,
        "auc_accepted_vs_declined": separation,
        "rho_across_rosters": across,
        "caution": "One venue, one rubric, ten reviews per paper. The comparison is between two readings of "
                   "the same reviews, so it says nothing about a grade read from one review.",
    }
    json.dump(result, open(a.out, "w", encoding="utf-8"), indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

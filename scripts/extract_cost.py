#!/usr/bin/env python3
"""Does a review that charges a property of the supplied text score the paper lower than one that does not?

The recommendation in §9 says a venue should show an author the text its reviewers were given. Two measurements
support it already: `extract_fidelity_corpus.py` shows what the pipeline drops, and `extract_charge_corpus.py`
shows that about one review in four charges the author for something that is a property of the drop. Neither
says whether the charge costs the paper anything. If it does not, the recommendation is about a reader's
experience; if it does, it is about a score.

The comparison is within paper. A paper's reviews differ in the score they give for every reason a reviewer can
differ, and the papers themselves differ far more than the reviews of any one of them, so a pooled split of
1,216 reviews would report the between-paper variance twice over. Each paper contributes the gap between the
mean composite of its reviews that make the charge and the mean of those that do not, and only papers with at
least one review on each side contribute at all.

What this cannot establish is direction. A review that dislikes a paper has more sentences of complaint in it
and so more chances to name the extract, which produces the same gap as an extract that costs the paper score.
The design that separates them is interventional -- supply the back matter to one arm and not the other -- and
that is a scoring run this measurement is not a substitute for. What the gap does bound is the size of the
thing being argued about: a gap indistinguishable from zero would leave §9's recommendation resting on the
reader's experience alone, whatever the direction.

    python3 extract_cost.py         # -> extract_cost.json + a table on stdout
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
CHARGE = "charge an extract-only property"


def load_reproduce():
    spec = importlib.util.spec_from_file_location("rp", f"{HERE}/reproduce.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_charge_corpus():
    """-> the module that owns the populations, the relabelling and the charge patterns."""
    spec = importlib.util.spec_from_file_location("ecc", f"{HERE}/extract_charge_corpus.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def calibrations():
    """-> {roster: calibration file}. One per roster, because the parameters are per (slot, metric) and the two
    rosters share no slot name. Standardising an eight-slot review against the five-slot table silently drops
    every review, and the first run of this script did exactly that: the population reported no papers at all.
    """
    CAL = {"five": "calibration_params_portable.json", "eight": "calibration_params_cursor8.json"}
    return {k: json.load(open(f"{HERE}/release/aina2026_agent_reviewers/calibration/{v}"))
            for k, v in CAL.items()}


def rows_by_paper(rp, ecc_mod, labels, cal):
    """-> {population: {paper: [(charge?, composite z)]}}, one entry per untouched third-party review.

    The one place a review becomes a (flag, score) pair. Anything else that needs the pair -- the score gap
    here, the bundle file the release ships so a reader can recompute it -- calls this, because two copies of
    the standardisation would be two definitions of the composite being compared.
    """
    pat = dict(rp.CHARGES)[CHARGE]
    out = {}
    for name, pattern in ecc_mod.POPULATIONS:
        c = cal["eight" if "eight slots" in name else "five"]
        mu, sd, metrics = c["mu"], c["sd"], c["metrics"]
        by_paper = {}
        for f in sorted(glob.glob(f"{HERE}/{pattern}")):
            rel = os.path.relpath(f, HERE)
            paper = ecc_mod.paper_of(rel, labels)
            if paper is None:
                continue
            r = json.load(open(f, encoding="utf-8"))
            slot = os.path.basename(f)[:2]
            zs = [(r["metrics"][m]["score"] - mu[f"{slot}|{m}"]) / sd[f"{slot}|{m}"]
                  for m in metrics if m in r.get("metrics", {}) and sd.get(f"{slot}|{m}")]
            if len(zs) != len(metrics):
                continue
            by_paper.setdefault(paper, []).append((rp.charges(r, pat), st.mean(zs)))
        out[name] = by_paper
    return out


def main():
    rp = load_reproduce()
    ecc_mod = load_charge_corpus()
    labels = ecc_mod.label_map()
    every = rows_by_paper(rp, ecc_mod, labels, calibrations())
    out = {}

    for name, pattern in ecc_mod.POPULATIONS:
        by_paper = every[name]
        gaps, both = [], []
        for paper, rows in sorted(by_paper.items()):
            hit = [z for c, z in rows if c]
            miss = [z for c, z in rows if not c]
            if hit and miss:
                both.append(paper)
                gaps.append(st.mean(hit) - st.mean(miss))
        lo, hi = rp.boot_ci(lambda g: st.median(g), gaps) if len(gaps) > 2 else (float("nan"),) * 2
        # The same question asked without the paper as the unit, kept for the contrast: it is the reading that
        # would be reported by anyone who pooled, and it carries the between-paper variance the paired one does
        # not. Printed beside the paired gap so the difference between the two is visible rather than argued.
        pool_hit = [z for rows in by_paper.values() for c, z in rows if c]
        pool_miss = [z for rows in by_paper.values() for c, z in rows if not c]
        out[name] = {
            "papers": len(by_paper), "papers_with_both": len(both),
            "reviews": sum(len(v) for v in by_paper.values()),
            "charging_reviews": len(pool_hit),
            "paired_gap_median": st.median(gaps) if gaps else None, "paired_ci": [lo, hi],
            "paired_positive": sum(1 for g in gaps if g > 0),
            "pooled_gap": st.mean(pool_hit) - st.mean(pool_miss) if pool_hit and pool_miss else None,
            "pooled_auc": rp.auc(pool_hit, pool_miss) if pool_hit and pool_miss else None,
        }

    w = max(len(n) for n, _ in ecc_mod.POPULATIONS)
    print(f"the composite gap between a paper's reviews that charge a property of the supplied text and its "
          f"reviews that do not,\nin standard deviations of the accepted set, paired within paper\n")
    for name, r in out.items():
        print(f"  {name:<{w}}  median {r['paired_gap_median']:+.3f}  "
              f"[{r['paired_ci'][0]:+.3f}, {r['paired_ci'][1]:+.3f}]  "
              f"{r['paired_positive']}/{r['papers_with_both']} papers positive")
    print("\nthe same reviews pooled, which is the reading that carries the between-paper variance:\n")
    for name, r in out.items():
        print(f"  {name:<{w}}  gap {r['pooled_gap']:+.3f}  AUC {r['pooled_auc']:.3f}  "
              f"{r['charging_reviews']} of {r['reviews']} reviews charge")

    json.dump(out, open(f"{HERE}/extract_cost.json", "w", encoding="utf-8"), indent=1)
    print("\nwrote extract_cost.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Are the reviews that charge an extract property the reviews of the papers whose extract lost something?

Two measurements exist separately. `extract_charge_corpus.py` gives the rate at which a review charges a
property of the supplied text rather than of the paper -- about one review in four, on both rosters and in both
corpora. `extract_fidelity_corpus.py` gives what each paper's supplied text actually lost: the back matter,
the pointers left behind in the body that now resolve to nothing, the captions, the words run together.

Two rates over the same 48 papers are consistent with the charge having nothing to do with the loss. What ties
them is a within-population association: the papers whose supplied text lost more should be the papers whose
reviews make the charge more often. That is the claim §9's recommendation rests on, and it is testable here
without a single new model call.

Length is the confound to rule out, in both directions: a longer submission has more back matter to lose and
more text to be charged for. So the same association is reported against the supplied text's own length, and
against the share of the body that survived, which is a ratio and not a size.

Populations are not pooled. The two corpora reach the panel through different pipelines -- preprint text one
side, the venue's de-identified PDF the other -- and pooling them would let a difference between corpora
appear as an association inside one.

    python3 extract_link.py         # -> extract_link.json + a table on stdout
"""
from __future__ import annotations

import importlib.util
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))

# Which charge population is measured on which set of documents. The eight-slot roster read the same sixteen
# accepted papers, so it is a second, independent read of the same extracts: an association that is real should
# appear in it too, and one that is a property of five particular slots should not.
PAIRS = [("accepted 16, five slots, untouched", "accepted 16, preprint text"),
         ("accepted 16, eight slots, untouched", "accepted 16, preprint text"),
         ("declined 32, five slots, untouched", "declined 32, as-submitted PDF")]
# Both reads of the same papers, averaged into one rate per paper. The number of papers is fixed at what the
# corpus holds, so the only precision left to buy is in the outcome: a paper's charge rate off ten or twenty
# reviews is a noisy estimate of the rate for that paper, and averaging the two reads halves that noise without
# pretending there are more papers than there are. Attenuation from a noisy outcome biases an association
# towards zero, which is the direction that would make a null here uninformative.
POOLED = [("accepted 16, both rosters", "accepted 16, preprint text",
           ["accepted 16, five slots, untouched", "accepted 16, eight slots, untouched"]),
          ("declined 32, both sittings", "declined 32, as-submitted PDF",
           ["declined 32, five slots, untouched"])]
# What in the supplied text might drive the charge, and which way the association should run if it does.
#
# Counts are read as densities. A pointer count is a length in disguise: a longer submission has more back
# matter to lose, more pointers left behind, and more text to be charged for, and the first run of this script
# showed exactly that -- the count of pointers correlated with the charge rate at +0.446 in the declined arm
# while the supplied text's own length correlated at +0.521. A count cannot separate the two and a density can,
# so every predictor here is per 1,000 supplied words or is already a ratio, and the raw count is kept only as
# the confounded quantity it is, reported beside its own control.
PREDICTORS = [("pointers per 1,000 words into back matter the reviewer lacks", "pointer_density", +1),
              ("share of the document's body supplied", "body_share", -1),
              ("captions per 1,000 words supplied", "caption_density", -1),
              ("words run together per 1,000", "fused_per_1k", +1),
              ("pointers into that back matter, as a count", "appendix_pointers", +1),
              ("length of the supplied text, as a control", "reviewer_words", 0)]
# The predictor whose association with the charge is the claim, and the control every reading of it is taken
# net of. Both are named here so the partial correlation below cannot quietly change which is which.
CLAIM, CONTROL = "pointer_density", "reviewer_words"
CHARGE = "charge an extract-only property"


def load_reproduce():
    spec = importlib.util.spec_from_file_location("rp", f"{HERE}/reproduce.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def densities(doc):
    """-> the document rows with every count also expressed per 1,000 words of the supplied text."""
    out = {}
    for paper, r in doc.items():
        w = max(r["reviewer_words"], 1) / 1000.0
        out[paper] = dict(r, pointer_density=r["appendix_pointers"] / w,
                          caption_density=r["reviewer_captions"] / w)
    return out


def partial(rp, xs, ys, zs):
    """-> (partial Spearman of x and y net of z, two-sided p), by the released definition.

    Holding the control fixed is the only reading that separates the claim from it: pointer count and supplied
    length are close to the same quantity, so an unadjusted rho cannot say which of them the reviewer is
    responding to.

    The arithmetic is `reproduce.py`'s, not this file's. "Net of" is a name for two different calculations --
    rank residuals, and the Pearson partial formula applied to ranks -- which differ by enough to matter, and
    the paper already prints a partial correlation computed the first way. A second definition here would put
    two quantities under one word in one appendix, and the one the bundle can recompute is the one that ships.
    """
    return rp.partial_spearman(ys, xs, zs)


def main():
    rp = load_reproduce()
    charges = json.load(open(f"{HERE}/extract_charge_corpus.json", encoding="utf-8"))["populations"]
    fidelity = json.load(open(f"{HERE}/extract_fidelity_corpus.json", encoding="utf-8"))
    out = {}

    reads = [(c, f, [c]) for c, f in PAIRS] + POOLED
    for cpop, fpop, members in reads:
        doc = densities(fidelity[fpop])
        papers = sorted(set.intersection(*[set(charges[m]["per_paper"]) for m in members]) & set(doc))
        assert len(papers) == len(doc), f"{cpop}: {len(papers)} of {len(doc)} papers have both measurements"
        # One rate per paper: the share of that paper's reviews that charge a property of the supplied text.
        # Averaged over the reads rather than pooled across them, so a read with more reviews per paper does
        # not carry more of the estimate than the paper's other read does.
        rate = [st.mean([charges[m]["per_paper"][p].get(CHARGE, 0) / charges[m]["per_paper"][p]["reviews"]
                         for m in members]) for p in papers]
        rows = {}
        for label, key, direction in PREDICTORS:
            xs = [doc[p][key] for p in papers]
            if any(x is None for x in xs):
                continue
            rho, p = rp.spearman_p(xs, rate)
            lo, hi = rp.boot_ci(lambda a, b: rp.spearman(a, b), xs, rate, paired=True)
            rows[label] = {"rho": rho, "p": p, "ci": [lo, hi], "n": len(papers),
                           "expected_sign": direction}
        # The claim net of the control, which is the only reading that separates the two.
        pr, pp = partial(rp, [doc[p][CLAIM] for p in papers], rate, [doc[p][CONTROL] for p in papers])
        out[cpop] = {"documents": fpop, "reads": members, "papers": len(papers),
                     "charge_rate": st.mean(rate),
                     "by_predictor": rows,
                     "claim_net_of_control": {"rho": pr, "p": pp, "n": len(papers),
                                              "claim": CLAIM, "control": CONTROL}}

    for cpop, r in out.items():
        print(f"{cpop}  ({r['papers']} papers, charge rate {r['charge_rate']:.3f})")
        for label, v in r["by_predictor"].items():
            flag = "" if not v["expected_sign"] else \
                ("  as expected" if v["rho"] * v["expected_sign"] > 0 else "  against the expected sign")
            print(f"  {label:<58s} rho {v['rho']:+.3f}  p {v['p']:.4f}  "
                  f"[{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]{flag}")
        c = r["claim_net_of_control"]
        print(f"  {'the first of those, net of that control':<58s} rho {c['rho']:+.3f}  p {c['p']:.4f}\n")

    json.dump(out, open(f"{HERE}/extract_link.json", "w", encoding="utf-8"), indent=1)
    print("wrote extract_link.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

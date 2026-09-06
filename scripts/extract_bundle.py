#!/usr/bin/env python3
"""Assemble the one file the release ships for the extract measurements, and nothing else.

Appendix A's numbers are measured on inputs the release cannot carry: the submitted PDFs of 32 declined
third-party papers, and the de-identified text each reviewer was handed. Neither may be redistributed. So the
paper's contract -- every printed number recomputable from the bundle -- is kept by shipping the derived rows
instead of the documents: per paper, what its supplied text lost; per review, whether it charged a property of
that text and what composite it gave.

What is in this file is counts, ratios and one boolean per review. What is not in it is any text, any title, any
forum id, and any review's free text. A declined paper appears under the arm-blind `R##` label the ranking study
already publishes, an accepted paper under its arXiv id, which is public.

The cross-check that makes this file evidence rather than assertion is in `reproduce.py`: for the two accepted
populations, whose reviews ship complete, it recomputes the charge flag from the shipped review text and refuses
a bundle whose flags disagree with the ones here. The declined populations cannot be checked that way -- their
reviews ship as scores only -- and the accepted check is what stands behind them, since one pattern produced
both.

    python3 extract_bundle.py       # -> extract_corpus.json
"""
from __future__ import annotations

import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/extract_corpus.json"
# Which set of documents each population of reviews was read from, so the association in reproduce.py joins the
# two halves of this file the way extract_link.py joins the two tool outputs.
DOCUMENTS = {"accepted 16, five slots, untouched": "accepted 16, preprint text",
             "accepted 16, eight slots, untouched": "accepted 16, preprint text",
             "declined 32, five slots, untouched": "declined 32, as-submitted PDF",
             "declined 32, five slots, ranking study": "declined 32, as-submitted PDF"}
# The fidelity fields the paper's numbers are computed from. Listed rather than copied wholesale, so a field
# added to the measurement for a later question does not silently enter the release.
FIELDS = ("document_words", "body_words", "back_words", "reviewer_words", "reviewer_body_words",
          "body_share", "section_symbol_refs", "reviewer_section_symbol_refs", "appendix_pointers",
          "captions", "reviewer_captions", "fused_per_1k", "source_fused_per_1k")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    cost = load("cost", f"{HERE}/extract_cost.py")
    rp = cost.load_reproduce()
    ecc = cost.load_charge_corpus()
    fidelity = json.load(open(f"{HERE}/extract_fidelity_corpus.json", encoding="utf-8"))
    every = cost.rows_by_paper(rp, ecc, ecc.label_map(), cost.calibrations())

    out = {"note": "Derived rows for appendix A's extract measurements. Per paper: what the text supplied to "
                   "the reviewer lost against the submitted document. Per review: whether it charged a "
                   "property of the supplied text, and the composite it gave, in standard deviations of the "
                   "accepted set. No document text, no review text and no forum id is here; reproduce.py "
                   "recomputes every printed number from these rows and re-derives the charge flags of the "
                   "accepted populations from the shipped reviews.",
           "documents": {}, "populations": {}}

    for pop, docs in fidelity.items():
        out["documents"][pop] = {paper: {k: r[k] for k in FIELDS} for paper, r in sorted(docs.items())}

    for pop, by_paper in every.items():
        rows = [{"paper": paper, "charge": bool(c), "z": z}
                for paper, rs in sorted(by_paper.items()) for c, z in rs]
        out["populations"][pop] = {"documents": DOCUMENTS[pop], "reviews": rows}

    # Nothing leaves here that names a submission. The labels are the published ones and the arXiv ids are
    # public, so what this refuses is an id that is neither: a bare OpenReview forum id, which is what every
    # directory these rows were read from is named by.
    ids = {r["paper"] for p in out["populations"].values() for r in p["reviews"]}
    ids |= {paper for d in out["documents"].values() for paper in d}
    bad = sorted(i for i in ids if not (i.startswith("R") and i[1:].isdigit())
                 and not all(c.isdigit() or c == "." for c in i))
    assert not bad, f"an identifier that is neither an R## label nor an arXiv id: {bad}"

    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    n_rev = sum(len(p["reviews"]) for p in out["populations"].values())
    n_doc = sum(len(d) for d in out["documents"].values())
    print(f"wrote extract_corpus.json: {n_doc} documents, {n_rev} reviews, "
          f"{sum(1 for p in out['populations'].values() for r in p['reviews'] if r['charge'])} charging")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

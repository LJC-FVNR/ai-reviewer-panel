#!/usr/bin/env python3
"""How often reviewers of the third-party corpus charge a property of the extract rather than of the paper.

Appendix A's artifact class was measured on one manuscript: the ten reviews of this submission, counted with
the patterns in `reproduce.py`. One document cannot say whether the class is a property of the extractor or a
property of that document, and the recommendation in section 9 is addressed to venues, which read other
people's papers. The corpus already scored answers the question directly: 1,856 untouched reviews of 48
third-party ICLR 2026 submissions, read through the same extractor, by the same slots, under the same prompt.

The patterns are imported, not restated. `reproduce.py` owns them, its expectation table checks the counts it
reports with them, and a second copy here would be a second definition of the thing being counted -- which is
the defect the comment above those patterns records.

Populations are kept apart rather than pooled, because they differ in what the reviewer was handed: the
accepted papers reach the panel as preprint-stage arXiv text, the declined ones as the as-submitted PDF the
venue de-identified, and the eight-slot roster read the accepted sixteen only. Pooling them would report a
rate for a corpus nobody scored.

No forum id enters the output. The ranking study's directories are named by forum id, so each is translated
through `reject_arm/public_labels.json` to its arm-blind `R##` label before anything is printed, and the
sampling stratum in the directory name is globbed past.

    python3 extract_charge_corpus.py            # -> extract_charge_corpus.json + a table on stdout
"""
from __future__ import annotations

import collections
import glob
import importlib.util
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def load_reproduce():
    spec = importlib.util.spec_from_file_location("rp", f"{HERE}/reproduce.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def label_map():
    """forum id -> R## label, read to relabel and never to print."""
    return json.load(open(f"{HERE}/reject_arm/public_labels.json", encoding="utf-8"))


def paper_of(path, labels):
    """-> the identifier this paper may be printed under, or None if the path is not a scored review."""
    parts = path.split("/")
    if parts[0] == "n1b_drift_5model":
        return parts[2]                              # an arXiv id: the accepted papers are public preprints
    if parts[0] == "n1c_reject_5model":
        return parts[2]                              # already an R## label
    if parts[0] == "n0_cursor8_iclr":
        return parts[2]
    if parts[0] == "reject_arm":
        # high_<forumid> / low_<forumid>: the stratum is dropped and the id is relabelled, so neither reaches
        # the output. A directory whose id is not in the map is a directory this study did not score.
        return labels.get(parts[2].split("_", 1)[1])
    return None


POPULATIONS = [
    ("accepted 16, five slots, untouched", "n1b_drift_5model/reviews/*/baseline/panel*/R?.json"),
    ("declined 32, five slots, untouched", "n1c_reject_5model/reviews/R*/baseline/panel*/R?.json"),
    ("accepted 16, eight slots, untouched", "n0_cursor8_iclr/reviews/*/panel*/[A-Z][0-9].json"),
]


def main():
    rp = load_reproduce()
    labels = label_map()
    out, examples = {}, collections.defaultdict(list)

    for name, pattern in POPULATIONS:
        files = sorted(glob.glob(f"{HERE}/{pattern}"))
        rows, papers = collections.Counter(), collections.defaultdict(set)
        # Per paper as well as per population, because the rate alone cannot say whether the reviews that make
        # this charge are the reviews of the papers whose supplied text actually lost something. That question
        # is asked in extract_link.py, and it needs a denominator per paper: reviews read, charges made.
        per_paper = collections.defaultdict(lambda: collections.Counter())
        seen_papers, n = set(), 0
        for f in files:
            rel = os.path.relpath(f, HERE)
            paper = paper_of(rel, labels)
            if paper is None:
                continue
            seen_papers.add(paper)
            n += 1
            r = json.load(open(f, encoding="utf-8"))
            per_paper[paper]["reviews"] += 1
            for charge, pat in rp.CHARGES:
                if rp.charges(r, pat):
                    rows[charge] += 1
                    papers[charge].add(paper)
                    per_paper[paper][charge] += 1
                    # Only reviews of the accepted sixteen are quotable: those reviews ship complete, while a
                    # declined submission's reviews ship as scores only, so a sentence quoted from one would be
                    # text about a third party's declined paper that no reader can check against the bundle.
                    if "accepted" in name:
                        target = pat[0] if isinstance(pat, tuple) else pat
                        for field in rp.strings(r):
                            m = re.search(target, field)
                            if m:
                                examples[charge].append({"paper": paper, "population": name,
                                                         "grade": r.get("grade") or r.get("overall_grade"),
                                                         "text": field.strip()})
                                break
        out[name] = {"reviews": n, "papers": len(seen_papers),
                     "by_charge": {c: {"reviews": rows[c], "papers": len(papers[c])} for c, _ in rp.CHARGES},
                     "per_paper": {p: dict(c) for p, c in sorted(per_paper.items())}}

    total_reviews = sum(v["reviews"] for v in out.values())
    print(f"{total_reviews} untouched third-party reviews\n")
    w = max(len(n) for n, _ in POPULATIONS)
    for charge, _ in rp.CHARGES:
        print(charge)
        for name, _ in POPULATIONS:
            v, b = out[name], out[name]["by_charge"][charge]
            share = b["reviews"] / v["reviews"] if v["reviews"] else 0.0
            print(f"  {name:<{w}}  {b['reviews']:4d} / {v['reviews']:4d} reviews  {share:6.3f}   "
                  f"{b['papers']:3d} / {v['papers']:3d} papers")
        print()

    json.dump({"populations": out, "quotable_examples": dict(examples)},
              open(f"{HERE}/extract_charge_corpus.json", "w", encoding="utf-8"), indent=1)
    print(f"wrote extract_charge_corpus.json "
          f"({sum(len(v) for v in examples.values())} quotable example(s) from the accepted sixteen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""paper/references.bib, generated from the arXiv API rather than typed.

A bibliography is the one part of a paper where a wrong field is invisible to every other check in this
repo: number_guard.py does not read it, the converter does not read it, and a plausible-looking wrong year
survives to print. So no field here is written by hand. The id list is the editorial decision; every title,
author list and year is whatever export.arxiv.org returns for that id, and an id that returns nothing is a
hard failure rather than a gap.

  python3 make_bib.py            # rewrite paper/references.bib
"""
from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

AN = os.path.dirname(os.path.abspath(__file__))
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}

# key -> arXiv id. Keys are cited from DRAFT.md as [@key]; see md2tex.py.
IDS = {
    "liang2023feedback": "2310.01783", "liu2023reviewergpt": "2306.00622", "darcy2024marg": "2401.04259",
    "ye2024risks": "2412.01708", "lu2024aiscientist": "2408.06292", "liang2024monitoring": "2403.07183",
    "latona2024lottery": "2405.02150", "zheng2023judging": "2306.05685", "wang2023unfair": "2305.17926",
    "stureborg2024inconsistent": "2405.01724", "panickssery2024own": "2404.13076",
    "sclar2023formatting": "2310.11324", "cortes2021inconsistency": "2109.09774",
    "beygelzimer2023arbitrary": "2306.03262", "kuznetsov2024nlp": "2405.06563", "gu2024survey": "2411.15594",
    "wu2023style": "2307.03025", "dubois2024length": "2404.04475", "liu2023geval": "2303.16634",
    # Added from the collision search in related_works/. The first three each independently establish
    # something the introduction had claimed was missing, so they are cited where that claim is made rather
    # than in a related-work list; the rest are the overlaps the same search turned up. See
    # related_works/COLLISIONS.md for what each one occupies and what it leaves.
    "yang2026presentation": "2606.13044",       # presentation-only revisions, adaptive attacker
    "georgantas2026firstpass": "2606.15887",    # a manuscript score validated against ICLR outcomes
    "kohli2026judges": "2605.29800",            # nine judges, two effective votes
    "kaneko2026paraphrase": "2601.06884",       # meaning-preserving paraphrase attack on LLM reviewers
    "li2025aspect": "2502.12510",               # aspect-guided perturbation of papers, reviews, rebuttals
    "sahoo2025injection": "2512.10449",         # indirect prompt injection flipping reject to accept
    "li2026benchmark": "2605.25415",            # 898 papers, 12 models, weaker submissions overrated
    "zheng2026ranking": "2603.17588",           # comparison-native ranking instead of absolute scoring
    "kosti2026meaning": "2602.17316",           # equivalent perturbations destabilise leaderboards
    "fichtl2026policies": "2608.03581",         # reviewer-facing AI policies across 111 venues
    "nguyen2026survey": "2606.25057",           # survey of LLM peer review
    "loc2026prism": "2605.26730",               # PRISM, a peer-reviewer benchmark
    "jiang2025badscientist": "2510.18003",      # fabricated papers passing multi-model review
    "chen2026epistemic": "2607.10511",          # epistemic reliability of judge-based review
}


def fetch(ids):
    q = urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids) + 5})
    # https, not http: the endpoint answers a plain-http request with a 301 whose body is empty, which parses
    # as no entries at all -- so every id looks missing and the assertion below blames the id list.
    root = ET.fromstring(urllib.request.urlopen("https://export.arxiv.org/api/query?" + q, timeout=90).read())
    out = {}
    for e in root.findall("a:entry", NS):
        aid = e.find("a:id", NS).text.rsplit("/", 1)[-1].split("v")[0]
        jref = e.find("x:journal_ref", NS)
        out[aid] = dict(
            title=" ".join(e.find("a:title", NS).text.split()),
            authors=[a.find("a:name", NS).text for a in e.findall("a:author", NS)],
            year=e.find("a:published", NS).text[:4],
            # arXiv carries a journal reference only when the authors added one, so most of these are
            # preprint-only. Reporting the preprint is honest; inventing a venue is not.
            jref=" ".join(jref.text.split()) if jref is not None else None,
        )
    return out


def cited():
    """-> every [@key] the paper actually cites, which is the other half of the id list."""
    keys = set()
    for path in ("DRAFT.md", "APPENDIX.md"):
        for m in re.finditer(r"@([A-Za-z][A-Za-z0-9]*)", open(f"{AN}/{path}", encoding="utf-8").read()):
            keys.add(m.group(1))
    return keys


def main():
    # The id list and the citations are two hand-maintained halves of one thing, and until now neither read
    # the other: a [@key] with no id here reaches LaTeX as an undefined citation and prints as a bare "?",
    # and an id nothing cites is invisible because bibtex only emits what is cited. Both directions are
    # derivable, so both are derived. Uncited ids are reported rather than fatal, because a citation and its
    # id do not have to land in the same edit.
    want = cited()
    undefined = sorted(want - set(IDS))
    assert not undefined, f"the paper cites {undefined} with no arXiv id in IDS"
    spare = sorted(set(IDS) - want)
    if spare:
        print(f"note: {len(spare)} id(s) in IDS that nothing cites yet: {', '.join(spare)}")

    # Only what the paper cites is written out. IDS is the record of everything the collision search found and
    # is worth keeping whole, but a .bib carrying entries nothing cites is a derived file that disagrees with
    # the document it was derived from, and bibtex prints none of them, so the difference is invisible until
    # someone reads the release and counts.
    emit = sorted(set(IDS) & want)
    got = fetch([IDS[k] for k in emit])
    missing = {k: IDS[k] for k in emit if IDS[k] not in got}
    assert not missing, f"arXiv returned no entry for {missing}; fix the id, do not fill it in by hand"

    lines = ["% Generated by make_bib.py from the arXiv API. Do not hand-edit; re-run the generator.",
             "% Each entry's title, author list and year are exactly what export.arxiv.org returned for its id.",
             "% Every entry here is cited; the generator's id list also records work the citation search found "
             "and the paper does not cite.", ""]
    for key in emit:
        m = got[IDS[key]]
        lines += ["@article{%s," % key,
                  "  title   = {{%s}}," % m["title"].replace("{", "").replace("}", ""),
                  "  author  = {%s}," % " and ".join(m["authors"]),
                  "  journal = {%s}," % (m["jref"] or f"arXiv preprint arXiv:{IDS[key]}"),
                  "  year    = {%s}," % m["year"],
                  "  url     = {https://arxiv.org/abs/%s}," % IDS[key],
                  "}", ""]
    open(f"{AN}/paper/references.bib", "w", encoding="utf-8").write("\n".join(lines))
    print(f"wrote paper/references.bib: {len(emit)} entries, one per cited key, all fields from the API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

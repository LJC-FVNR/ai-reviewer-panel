#!/usr/bin/env python3
"""What the instrument's text pipeline does to a submitted document, measured on all 48 corpus papers.

Appendix A's artifact class was measured on one document -- the manuscript being submitted -- and one document
cannot say whether a loss is a property of the pipeline or a property of that file. Both arms of the corpus
keep the pair the measurement needs: the document as submitted, and the text the reviewer was handed.

    accepted 16   dir98/pdfs/<arxiv id>v<n>.pdf        dir98/deid/build_<arxiv id>/manuscript.txt
    declined 32   reject_arm/pdfs/<arm>_<forum>.pdf    reject_arm/deid/build_<arm>_<forum>/manuscript.txt

Both sides are read with the same tool the pipeline itself uses, `pdftotext` with default flags, so what the
comparison isolates is the de-identifying rebuild between them and not a second text extractor's habits. The
reviewer's side is the file the panel actually read, byte for byte, not a re-extraction of it.

The reference list is located by its heading with the spaces removed, because the venue template sets headings
in spaced small caps and `pdftotext` returns "R EFERENCES". A paper whose heading cannot be found is counted
and excluded from the rows that need the body/back-matter split, rather than silently given the whole document
as its body.

No forum id enters the output. A declined paper is printed under the arm-blind `R##` label that
`reject_arm/public_labels.json` assigns it, and the sampling stratum in the directory name is dropped.

    python3 extract_fidelity_corpus.py      # -> extract_fidelity_corpus.json + a table on stdout
"""
from __future__ import annotations

import json
import os
import re
import statistics as st
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DIR98 = "/path/to/workspace/paper_direction_98_calibration"
CACHE = "/tmp/extract_fidelity_src"

# The heading, with every space removed, that starts the back matter. "R EFERENCES" and "REFERENCES" both
# normalise to the same string, and so does a numbered "8 References".
BACK = re.compile(r"^(?:\d+)?(?:references|bibliography)$")
# A cross-reference written with the section symbol. The pipeline keeps printable ASCII only, so every one of
# these is a reference the reviewer is left holding a dangling number for.
SECT = re.compile(r"§\s*\d")
# A pointer into the back matter, in the text the reviewer was given.
APPX = re.compile(r"\bAppendi(?:x|ces)\s+[A-Z]\b")
CAPT = re.compile(r"(?m)^\s*(?:Table|Figure)\s+\d+\s*[:.]")
# Two words run together where the space was lost, as "theWeight". Three letters on each side, so an ordinary
# camel-cased name is not counted as a fusion.
FUSED = re.compile(r"[a-z]{3,}[A-Z][a-z]{3,}")


def pdftotext(path):
    """-> the document's text, cached, read the way the pipeline reads it."""
    os.makedirs(CACHE, exist_ok=True)
    out = f"{CACHE}/{re.sub(r'[^A-Za-z0-9._-]', '_', path)}.txt"
    if not os.path.exists(out):
        subprocess.run(["pdftotext", path, out], capture_output=True, check=True)
    return open(out, encoding="utf-8", errors="replace").read()


def split_back(text):
    """-> (body, back matter, located?): the document cut at its reference list."""
    at = None
    for m in re.finditer(r"(?m)^(.+)$", text):
        line = re.sub(r"[^A-Za-z0-9]", "", m.group(1)).lower()
        if BACK.match(line) and len(m.group(1)) < 40:
            at = m.start()                      # the last one, so a table of contents entry does not win
    if at is None:
        return text, "", False
    return text[:at], text[at:], True


def measure(src, rev):
    body, back, located = split_back(src)
    rbody, rback, rlocated = split_back(rev)
    w = lambda t: len(t.split())
    return {
        "located": located, "reviewer_located": rlocated,
        "document_words": w(src), "body_words": w(body), "back_words": w(back),
        "reviewer_words": w(rev), "reviewer_body_words": w(rbody), "reviewer_back_words": w(rback),
        # The supplied text is cut at the reference list by design, so it has no back matter to find and
        # `reviewer_located` is a report on the pipeline rather than a condition on this ratio. What the ratio
        # asks is how much of the document's body -- everything before the references -- the reviewer got.
        "body_share": w(rbody) / w(body) if located and w(body) else None,
        "section_symbol_refs": len(SECT.findall(src)), "reviewer_section_symbol_refs": len(SECT.findall(rev)),
        "appendix_pointers": len(APPX.findall(rev)),
        "captions": len(CAPT.findall(src)), "reviewer_captions": len(CAPT.findall(rev)),
        "fused_per_1k": 1000 * len(FUSED.findall(rev)) / max(w(rev), 1),
        "source_fused_per_1k": 1000 * len(FUSED.findall(src)) / max(w(src), 1),
    }


def populations():
    """-> [(population, {paper: (source pdf, reviewer text)})], declined papers relabelled."""
    acc = {}
    for d in sorted(os.listdir(f"{DIR98}/deid")):
        if not d.startswith("build_"):
            continue
        pid = d[len("build_"):]
        pdfs = sorted(f for f in os.listdir(f"{DIR98}/pdfs") if f.startswith(pid))
        if pdfs and os.path.exists(f"{DIR98}/deid/{d}/manuscript.txt"):
            acc[pid] = (f"{DIR98}/pdfs/{pdfs[-1]}", f"{DIR98}/deid/{d}/manuscript.txt")

    labels = json.load(open(f"{HERE}/reject_arm/public_labels.json", encoding="utf-8"))
    dec = {}
    for d in sorted(os.listdir(f"{HERE}/reject_arm/deid")):
        if not d.startswith("build_"):
            continue
        eid = d[len("build_"):]                       # <arm>_<forum id>: the arm is dropped here
        label = labels.get(eid.split("_", 1)[1])
        pdf = f"{HERE}/reject_arm/pdfs/{eid}.pdf"
        if label and os.path.exists(pdf) and os.path.exists(f"{HERE}/reject_arm/deid/{d}/manuscript.txt"):
            dec[label] = (pdf, f"{HERE}/reject_arm/deid/{d}/manuscript.txt")
    return [("accepted 16, preprint text", acc), ("declined 32, as-submitted PDF", dec)]


def main():
    out = {}
    for name, papers in populations():
        rows = {}
        for paper, (pdf, txt) in sorted(papers.items()):
            rows[paper] = measure(pdftotext(pdf), open(txt, encoding="utf-8", errors="replace").read())
        out[name] = rows

    def med(rows, key):
        vals = [r[key] for r in rows.values() if r[key] is not None]
        return st.median(vals) if vals else None

    for name, rows in out.items():
        n = len(rows)
        print(f"{name}: {n} papers, "
              f"{sum(1 for r in rows.values() if r['located'])} with a reference list located\n")
        print(f"  submitted document, words        median {med(rows, 'document_words'):.0f}")
        print(f"  text supplied to the reviewer    median {med(rows, 'reviewer_words'):.0f}")
        print(f"  share of the body supplied       median {med(rows, 'body_share'):.3f}")
        print(f"  back matter, words               median {med(rows, 'back_words'):.0f} in the document, "
              f"and {sum(1 for r in rows.values() if r['reviewer_located'])} of {n} supplied texts have any")
        loses = [p for p, r in rows.items() if r["section_symbol_refs"] and not r["reviewer_section_symbol_refs"]]
        has = [p for p, r in rows.items() if r["section_symbol_refs"]]
        print(f"  cross-references written with the section symbol: {len(has)} of {n} papers have any, "
              f"median {med({p: rows[p] for p in has}, 'section_symbol_refs') or 0:.0f}, "
              f"and {len(loses)} of {len(has)} lose every one")
        ptr = [p for p, r in rows.items() if r["appendix_pointers"]]
        print(f"  the supplied text points into back matter it does not contain: {len(ptr)} of {n} papers, "
              f"median {med({p: rows[p] for p in ptr}, 'appendix_pointers') or 0:.0f} pointers")
        print(f"  table and figure captions        median {med(rows, 'captions'):.0f} in the document, "
              f"{med(rows, 'reviewer_captions'):.0f} supplied")
        print(f"  words run together per 1,000     median {med(rows, 'fused_per_1k'):.2f} supplied, "
              f"{med(rows, 'source_fused_per_1k'):.2f} in the document\n")

    json.dump(out, open(f"{HERE}/extract_fidelity_corpus.json", "w", encoding="utf-8"), indent=1)
    print("wrote extract_fidelity_corpus.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Did T3 (join sentences) reach inside caption blocks?

F4 charges each transform only for the channels it may legitimately move, so T3's figure_quality drop
(-0.240) is a leak only if joining PROSE sentences left the caption blocks alone. Whether it did is a
property of the variant texts rather than of the transform's intent, and this script measures it.

The definition of a caption block is taken verbatim from pia_transforms.PLACEHOLDER rather than
re-invented here: a block is the `[Figure N about here]` / `[Table N about here]` line plus the
following non-blank lines, up to the next blank line or the next placeholder. A looser "anything
starting with Figure/Table" regex counts running-text references to figures as well and inflates the
number roughly twofold. Any caption-reach number quoted in the paper must come from this script.

Counting rule: a caption line is CHANGED if its exact text appears in the baseline's caption blocks
and not in the variant's. Sets, not diff hunks -- T1 relocates blocks wholesale, so a positional
diff reports every caption line in the paper as moved and says nothing about rewriting. All three
transforms are audited, because the interesting result would be T1 or T2 rewriting a caption they
had no business rewriting.

Reads pia_variants/. Prints one row per (paper, transform) and a per-transform total. With --json it also
writes caption_reach.json, which is what the appendix reads; the printed table stays the record of which
paper contributed what.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pia_transforms import PLACEHOLDER  # the one definition of a caption block

AN = os.path.dirname(os.path.abspath(__file__))
# Both variant trees. Caption reach is a property of the texts, so it is not gated by scoring, and the
# appendix quotes it as a corpus fact -- which it stops being if the corpus grows and the audit does not.
TREES = [os.path.join(AN, "pia_variants"), os.path.join(AN, "pia_variants_reject")]
V = TREES[0]
TRANSFORMS = ("T1_endmatter", "T2_concede", "T3_lengthen")


def caption_lines(text):
    """Every line inside a placeholder-anchored caption block, placeholder line excluded."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if not PLACEHOLDER.match(lines[i].strip()):
            i += 1
            continue
        i += 1
        while i < len(lines) and lines[i].strip() and not PLACEHOLDER.match(lines[i].strip()):
            out.append(lines[i].strip())
            i += 1
    return out


def prose_lines(text):
    """Every non-blank line OUTSIDE a caption block: the complement of caption_lines over the same split.

    The complement rather than a second definition, because the interesting claim about T1 is a negative one
    -- it relocates blocks and rewrites nothing -- and a negative measured against a looser notion of "prose"
    than the one caption_lines uses would be true of whatever the two definitions disagree about.
    """
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if not PLACEHOLDER.match(lines[i].strip()):
            if lines[i].strip():
                out.append(lines[i].strip())
            i += 1
            continue
        i += 1
        while i < len(lines) and lines[i].strip() and not PLACEHOLDER.match(lines[i].strip()):
            i += 1
    return out


def gone(base, var):
    """How many of `base`'s lines are absent from `var`, multiset-safe."""
    rem, n = list(var), 0
    for ln in base:
        if ln in rem:
            rem.remove(ln)
        else:
            n += 1
    return n


def main():
    trees = [t for t in TREES if os.path.exists(os.path.join(t, "manifest.json"))]
    items, npap, drop = [], {}, set()
    for tree in trees:
        man = json.load(open(os.path.join(tree, "manifest.json")))
        npap[tree] = len(man["papers"])
        items += [(tree, pid) for pid in man["papers"]]
        # Cells withheld from the scoring queue for falling under the pre-registered strength floor. They
        # were still WRITTEN, so their files exist and a tree walk finds them. Counting them would describe
        # a corpus that produced no delta, which is the opposite of what a leak audit is for.
        drop |= {(e["paper"], e["transform"]) for e in man.get("excluded", [])}
    tot = {t: 0 for t in TRANSFORMS}
    hit = {t: 0 for t in TRANSFORMS}
    seen = {t: 0 for t in TRANSFORMS}
    # The same counting rule run over the complement of the caption blocks. Kept beside the caption count
    # rather than in its own script because the two together are what an arm's description has to be true of:
    # T1 is described as relocating blocks, which is a claim about prose as much as about captions.
    pro_gone = {t: 0 for t in TRANSFORMS}
    pro_new = {t: 0 for t in TRANSFORMS}
    pro_hit = {t: 0 for t in TRANSFORMS}
    n_caps = n_pros = 0
    print(f"{'paper':12s} {'capln':>6s} " + " ".join(f"{t.split('_')[0]:>12s}" for t in TRANSFORMS))
    for tree, pid in items:
        d = os.path.join(tree, pid)
        btxt = open(os.path.join(d, "baseline.txt"), encoding="utf-8").read()
        base, bpro = caption_lines(btxt), prose_lines(btxt)
        n_caps += len(base)
        n_pros += len(bpro)
        row = []
        for t in TRANSFORMS:
            vf = os.path.join(d, f"{t}.txt")
            if (pid, t) in drop or not os.path.exists(vf):
                row.append(None)
                continue
            seen[t] += 1
            vtxt = open(vf, encoding="utf-8").read()
            # multiset-safe: identical duplicate caption lines are rare but must not cancel out
            n = gone(base, caption_lines(vtxt))
            tot[t] += n
            hit[t] += 1 if n else 0
            vpro = prose_lines(vtxt)
            g = gone(bpro, vpro)
            pro_gone[t] += g
            pro_new[t] += gone(vpro, bpro)
            pro_hit[t] += 1 if g else 0
            row.append(n)
        print(f"{pid:12s} {len(base):6d} " +
              " ".join(f"{'   withheld' if v is None else v:>12}" for v in row))
    print(f"\n{n_caps} caption lines and {n_pros} prose lines across {len(items)} papers "
          f"({', '.join(f'{os.path.basename(t)} {n}' for t, n in npap.items())})")
    for t in TRANSFORMS:
        print(f"  {t:14s} changed {tot[t]:3d} caption lines "
              f"({100.0 * tot[t] / max(1, n_caps):.1f}%) in {hit[t]} of {seen[t]} papers")
    for t in TRANSFORMS:
        print(f"  {t:14s} baseline prose lines gone {pro_gone[t]:5d} in {pro_hit[t]:2d} of {seen[t]} papers, "
              f"prose lines the variant adds {pro_new[t]:5d}")
    if "--json" in sys.argv:
        out = {"n_caption_lines": n_caps, "n_prose_lines": n_pros, "n_papers": len(items),
               "papers_per_tree": {os.path.basename(t): n for t, n in npap.items()},
               "per_transform": {t: {"lines_changed": tot[t],
                                     "pct_of_caption_lines": round(100.0 * tot[t] / max(1, n_caps), 1),
                                     "papers_touched": hit[t], "papers_scored": seen[t],
                                     "prose_lines_gone": pro_gone[t], "prose_lines_new": pro_new[t],
                                     "prose_papers_touched": pro_hit[t]}
                                 for t in TRANSFORMS}}
        with open(os.path.join(AN, "caption_reach.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
        print("\nwrote caption_reach.json")

    print("\nQUOTE THESE NUMBERS, not a hand diff. A non-zero count settles figure_quality as legitimate "
          "for that arm; a zero count does not settle it as a leak, and fig4.LEGIT allots figure_quality "
          "to T1 as well, on the ground that relocating a figure separates it from the sentence that "
          "refers to it. This audit answers whether captions changed, not what an arm may be charged for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fetch final human review scores for every ICLR-2026 interpretability submission.

One /notes?forum=... call per paper, checkpointed every 25 papers. Gives the venue's
own post-rebuttal ratings, which the HuggingFace snapshot does not (its ratings are
pre-rebuttal initial scores).
"""
import json
import os
import statistics as st
import sys
from collections import Counter

from or_client import OR

AREA = "interpretability and explainable AI"
OUT = "iclr2026_interp_reviews.json"

frame = json.load(open("iclr2026_frame.json"))
pool = [r for r in frame if r["area"] == AREA]
have = json.load(open(OUT)) if os.path.exists(OUT) else {}
todo = [r for r in pool if r["forum"] not in have]
print(f"{len(pool)} interpretability papers, {len(have)} cached, {len(todo)} to fetch", flush=True)

c = OR()
FIELDS = ("rating", "confidence", "soundness", "presentation", "contribution")


def num(v):
    if v is None:
        return None
    s = str(v).strip()
    for tok in (s.split(":")[0], s.split()[0] if s.split() else s):
        try:
            return float(tok)
        except ValueError:
            continue
    return None


for i, r in enumerate(todo):
    notes = c.get("/notes", forum=r["forum"],
                  select="id,invitations,content.rating,content.confidence,content.soundness,"
                         "content.presentation,content.contribution,content.decision")["notes"]
    revs, dec = [], None
    for n in notes:
        inv = " ".join(n.get("invitations", []))
        g = lambda k: (n.get("content", {}).get(k) or {}).get("value")
        if "Official_Review" in inv:
            d = {f: num(g(f)) for f in FIELDS}
            if d["rating"] is not None:
                revs.append(d)
        elif "Decision" in inv:
            dec = g("decision")
        elif "Withdrawal" in inv and dec is None:
            dec = "Withdrawn"
    rt = [x["rating"] for x in revs]
    have[r["forum"]] = dict(
        forum=r["forum"], id=r["id"], title=r["title"], venueid=r["venueid"], venue=r["venue"],
        decision=dec, nrev=len(revs), reviews=revs,
        rating_mean=round(st.mean(rt), 4) if rt else None,
        rating_min=min(rt) if rt else None, rating_max=max(rt) if rt else None,
        rating_sd=round(st.stdev(rt), 4) if len(rt) > 1 else 0.0)
    if (i + 1) % 25 == 0 or i + 1 == len(todo):
        json.dump(have, open(OUT, "w"))
        print(f"  [{i+1}/{len(todo)}] cached {len(have)}", flush=True)

json.dump(have, open(OUT, "w"))
acc = [v for v in have.values() if v["venueid"] == "ICLR.cc/2026/Conference"]
rej = [v for v in have.values() if v["venueid"].endswith("Rejected_Submission")]
for tag, g in (("accepted", acc), ("rejected", rej)):
    rr = [v["rating_mean"] for v in g if v["rating_mean"] is not None]
    print(f"{tag:9s} n={len(g):4d} with_ratings={len(rr):4d} "
          f"mean={st.mean(rr):.2f} median={st.median(rr):.2f} "
          f"min={min(rr):.2f} max={max(rr):.2f}")
print("decision labels:", dict(Counter(str(v["decision"])[:40] for v in have.values()).most_common(8)))

#!/usr/bin/env python3
"""Build the authoritative ICLR-2026 outcome frame from the OpenReview API.

Output `iclr2026_frame.json`: one row per submission with the venue's own decision
label (`venueid`/`venue`), the PDF path, primary area, and title. This replaces the
HuggingFace snapshot's inferred labels with the venue's own.
"""
import json
from collections import Counter

from or_client import OR

BUCKETS = [
    "ICLR.cc/2026/Conference",                              # accepted (Poster/Spotlight/Oral)
    "ICLR.cc/2026/Conference/Rejected_Submission",
    "ICLR.cc/2026/Conference/Withdrawn_Submission",
    "ICLR.cc/2026/Conference/Desk_Rejected_Submission",
]
SEL = "id,forum,content.title,content.venue,content.venueid,content.primary_area,content.pdf,cdate,mdate,pdate"

c = OR()
print("logged in as", c.user, flush=True)

rows, seen = [], set()
for vid in BUCKETS:
    n0 = len(rows)
    for n in c.notes(page=1000, select=SEL, **{"content.venueid": vid}):
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        g = lambda k: (n.get("content", {}).get(k) or {}).get("value")
        rows.append(dict(id=n["id"], forum=n.get("forum", n["id"]), title=g("title"),
                         venue=g("venue"), venueid=g("venueid"), area=g("primary_area"),
                         pdf=g("pdf"), cdate=n.get("cdate"), mdate=n.get("mdate"),
                         pdate=n.get("pdate")))
    print(f"{vid:56s} {len(rows)-n0:6d}", flush=True)

json.dump(rows, open("iclr2026_frame.json", "w"))
print(f"\ntotal {len(rows)} submissions")
print("by outcome:", dict(Counter(r["venueid"].split("/")[-1] for r in rows)))
print("by venue string:", dict(Counter(r["venue"] for r in rows).most_common(8)))
interp = [r for r in rows if r["area"] == "interpretability and explainable AI"]
print(f"\ninterpretability and explainable AI: {len(interp)}")
print("  by outcome:", dict(Counter(r["venueid"].split("/")[-1] for r in interp)))
print("  accepted by venue:", dict(Counter(r["venue"] for r in interp
                                           if r["venueid"] == "ICLR.cc/2026/Conference")))

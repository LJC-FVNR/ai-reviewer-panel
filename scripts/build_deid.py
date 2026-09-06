#!/usr/bin/env python3
"""De-identify every downloaded sample PDF into a blind review manuscript.

Same reconstruction pipeline as the preprint arm (`deid_conference.py`), with the one
documented addition of the line-number-gutter filter. The true title comes from the
OpenReview record rather than from font-size heuristics, because the ICLR template sets
the title in spaced small caps that the heuristic mangles.

Resumable: a build directory with a non-trivial manuscript.txt is left alone.
"""
import json
import os
import subprocess
import sys

SAMPLE = "sample_preregistered.json"
INDEX = "deid_index.json"
s = json.load(open(SAMPLE))
idx = json.load(open(INDEX)) if os.path.exists(INDEX) else {}
os.makedirs("deid", exist_ok=True)
only = sys.argv[1:] or None

built = skipped = 0
for p in s["papers"]:
    if only and p["forum"] not in only:
        continue
    fp = p.get("pdf_file")
    if not (fp and os.path.exists(fp) and os.path.getsize(fp) > 20000):
        print(f"  -- {p['forum']}: pdf not downloaded yet", flush=True)
        continue
    eid = f"{p['arm']}_{p['forum']}"
    out = f"deid/build_{eid}"
    mtxt = f"{out}/manuscript.txt"
    if os.path.exists(mtxt) and os.path.getsize(mtxt) > 4000 and p["forum"] in idx:
        skipped += 1
        continue
    r = subprocess.run(["python3", "deid_iclr_submission.py", fp, "", out, p["title"]],
                       capture_output=True, text=True)
    if not os.path.exists(f"{out}/main.pdf"):
        print(f"  !! {eid}: no main.pdf  {r.stdout.strip()} {r.stderr.strip()[:160]}", flush=True)
        continue
    subprocess.run(["pdftotext", f"{out}/main.pdf", mtxt], capture_output=True)
    words = len(open(mtxt, errors="replace").read().split())
    units = next((l.split(":")[1].strip() for l in r.stdout.splitlines()
                  if l.startswith("UNITS")), "?")
    pages = subprocess.run(["pdfinfo", f"{out}/main.pdf"], capture_output=True, text=True).stdout
    pages = next((l.split(":")[1].strip() for l in pages.splitlines() if l.startswith("Pages")), "?")
    idx[p["forum"]] = dict(forum=p["forum"], arm=p["arm"], deid_dir=out, deid_words=words,
                           deid_units=int(units) if units.isdigit() else None,
                           deid_pages=int(pages) if pages.isdigit() else None,
                           src_pages=p.get("pages"), rating_mean=p["rating_mean"])
    json.dump(idx, open(INDEX, "w"), indent=1)
    built += 1
    print(f"  {eid:<26} units={units:>4} words={words:>6} pages={pages}", flush=True)

json.dump(idx, open(INDEX, "w"), indent=1)
done = list(idx.values())
print(f"\nbuilt {built}, already present {skipped}, total de-identified {len(done)}/32")
for arm in ("low", "high"):
    w = [p["deid_words"] for p in done if p["arm"] == arm]
    if w:
        print(f"  {arm:<5} n={len(w)} words mean={sum(w)/len(w):.0f} min={min(w)} max={max(w)}")

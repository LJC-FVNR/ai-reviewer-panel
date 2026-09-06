#!/usr/bin/env python3
"""Compute the ICLR calibration_params_portable.json from the parsed exemplar panel reviews.

Method (skill 18):
  * z-standardize each (reviewer-slot x metric) channel against the calibration-set mean/std.
  * A paper's composite = mean over (slot,metric) z, averaged over its panels.
  * Gate = median composite of the like-for-type accepted-ICLR exemplar subset (here: ALL exemplars,
    since the whole set is our type — mechanistic-interpretability / analysis-of-LLM-internals).
  * Also report the field median, per-paper composites, grade distribution, test-retest noise,
    and the fraction of reviews at Minor-Revision-or-better (the >60% project bar reference).

Output format matches the NMI calibration_params_portable.json so score_against_gate.py works unchanged.
"""
import json, os, glob, statistics, sys

REVROOT = sys.argv[1] if len(sys.argv) > 1 else "reviews"
OUT = sys.argv[2] if len(sys.argv) > 2 else "ICLR/calibration_params_portable.json"
SLOTS = ["R1", "R2", "R3", "R4", "R5"]
METRICS = ["significance", "novelty", "rigor", "statistical_soundness", "calibration_honesty",
           "clarity", "structure_compliance", "reproducibility", "related_work",
           "figure_quality", "breadth_generality", "overall_recommendation"]
PANEL_MODELS = {
    "R1": "gpt-5.5:codex", "R2": "gpt-5.4:codex",
    "R3": "us.anthropic.claude-opus-4-8[1m]:claude",
    "R4": "us.anthropic.claude-opus-4-7[1m]:claude",
    "R5": "us.anthropic.claude-sonnet-4-6[1m]:claude"}
MINOR_OR_BETTER = {"Accept", "Minor Revision"}

def load():
    papers = {}
    for pdir in sorted(glob.glob(os.path.join(REVROOT, "*"))):
        eid = os.path.basename(pdir)
        panels = {}
        for pan in sorted(glob.glob(os.path.join(pdir, "panel*"))):
            rows = {}
            for slot in SLOTS:
                f = os.path.join(pan, f"{slot}.json")
                if os.path.exists(f):
                    try:
                        rows[slot] = json.load(open(f))
                    except Exception:
                        pass
            if rows:
                panels[os.path.basename(pan)] = rows
        if panels:
            papers[eid] = panels
    return papers

def main():
    papers = load()
    # 1) per-(slot,metric) mu/sd over ALL exemplar reviews
    channel = {f"{s}|{m}": [] for s in SLOTS for m in METRICS}
    grades = []
    for eid, panels in papers.items():
        for pan, rows in panels.items():
            for slot, rev in rows.items():
                grades.append(rev.get("grade"))
                mets = rev.get("metrics", {})
                for m in METRICS:
                    if m in mets:
                        channel[f"{slot}|{m}"].append(mets[m]["score"])
    mu, sd = {}, {}
    for k, vals in channel.items():
        if vals:
            mu[k] = round(statistics.mean(vals), 4)
            sd[k] = round(statistics.pstdev(vals) if len(vals) > 1 else 1.0, 4)
            if sd[k] == 0:
                sd[k] = 1.0
    # 2) per-paper composite (mean over panels of mean over (slot,metric) z)
    def paper_composite(panels):
        pm = []
        for pan, rows in panels.items():
            zs = []
            for slot, rev in rows.items():
                mets = rev.get("metrics", {})
                for m in METRICS:
                    key = f"{slot}|{m}"
                    if m in mets and key in mu:
                        zs.append((mets[m]["score"] - mu[key]) / sd[key])
            if zs:
                pm.append(statistics.mean(zs))
        return statistics.mean(pm) if pm else None, pm
    per_paper = {}
    per_paper_panels = {}
    noise = []
    for eid, panels in papers.items():
        comp, pm = paper_composite(panels)
        per_paper[eid] = round(comp, 4) if comp is not None else None
        per_paper_panels[eid] = [round(x, 4) for x in pm]
        if len(pm) >= 2:
            noise.append(abs(pm[0] - pm[1]))
    comps = [c for c in per_paper.values() if c is not None]
    gate = round(statistics.median(comps), 4)
    field_median = gate  # whole set is like-type
    # grade distribution + minor-or-better fraction
    from collections import Counter
    gd = Counter(grades)
    minor_plus = sum(1 for g in grades if g in MINOR_OR_BETTER)
    out = {
        "venue": "ICLR",
        "venue_year": 2026,
        "paper_type": "mechanistic-interpretability / causal-analysis of LLM internals",
        "panel": [f"{s}:{PANEL_MODELS[s]}" for s in SLOTS],
        "metrics": METRICS,
        "mu": mu, "sd": sd,
        "per_paper_composite": per_paper,
        "per_paper_panel_composites": per_paper_panels,
        "gate_methods_cluster_median": gate,
        "published_field_median": field_median,
        "n_exemplars": len(papers),
        "n_reviews": len(grades),
        "grade_distribution": dict(gd),
        "minor_or_better_fraction": round(minor_plus / len(grades), 4) if grades else None,
        "noise_estimate": round(statistics.mean(noise), 4) if noise else None,
        "noise_estimate_note": "mean |panel1-panel2| paper composite; treat composite diffs below this as ties",
        "acceptance_provenance": "arXiv comment field = 'Accepted/Published at ICLR 2026' (main conference, workshop excluded); OpenReview api2 was challenge-gated in-sandbox so acceptance verified via arXiv, not OpenReview cross-check",
        "note": "composite = mean over (slot,metric) z=(score-mu)/sd, averaged over >=2 panels. PASS if composite >= gate_methods_cluster_median (= median composite of accepted like-type ICLR-2026 exemplars). Valid ONLY for this exact 5-model panel + reviewer_prompt_iclr.md. Whole calibration set is like-type, so gate == field median. Re-run calibration if panel/venue/prompt changes."
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"exemplars={len(papers)} reviews={len(grades)} gate(median)={gate} field={field_median}")
    print(f"noise={out['noise_estimate']} minor+={out['minor_or_better_fraction']} grades={dict(gd)}")
    print("per-paper composite:")
    for eid, c in sorted(per_paper.items(), key=lambda x: (x[1] is None, x[1])):
        print(f"  {eid}: {c}  panels={per_paper_panels[eid]}")
    print("wrote", OUT)

if __name__ == "__main__":
    main()

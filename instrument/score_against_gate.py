#!/usr/bin/env python3
"""Compute a manuscript's z-standardized composite from its panel reviews and compare to the
calibration gate. This is the tool the measured-revision GATE depends on — without it, workers
would have to hand-compute the composite (the failure mode the playbook warns against).

Usage:
    score_against_gate.py --reviews <dir-with-panel{1,2}/R{1..5}.json> \
        --calib <calibration_params_portable.json> [--label NAME] [--json]

The reviews dir must contain panel subdirs (panel1, panel2, ...) each with R1.json..R5.json,
each a parsed review (schema: metrics.<name>.score). Composite =
mean over selected (slot,metric) channels of z=(score-mu[slot|metric])/sd[slot|metric],
averaged over the panels. PASS if composite >= gate_methods_cluster_median.
"""
from __future__ import annotations
import argparse, json, os, statistics, sys, glob

def load_panels(reviews_dir):
    panels = {}
    for pdir in sorted(glob.glob(os.path.join(reviews_dir, "panel*"))):
        rows = {}
        for slot in ["R1", "R2", "R3", "R4", "R5"]:
            f = os.path.join(pdir, f"{slot}.json")
            if os.path.exists(f):
                rows[slot] = json.load(open(f))
        if rows:
            panels[os.path.basename(pdir)] = rows
    return panels

def composite(panels, mu, sd, metrics):
    panel_means = []
    for pname, rows in panels.items():
        zs = []
        for slot, rev in rows.items():
            m = rev.get("metrics", {})
            for metric in metrics:
                key = f"{slot}|{metric}"
                if metric in m and key in mu:
                    zs.append((m[metric]["score"] - mu[key]) / sd[key])
        if zs:
            panel_means.append(statistics.mean(zs))
    return statistics.mean(panel_means) if panel_means else None, len(panel_means)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviews", required=True)
    ap.add_argument("--calib", required=True)
    ap.add_argument("--label", default="manuscript")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cal = json.load(open(a.calib))
    mu, sd, metrics = cal["mu"], cal["sd"], cal["metrics"]
    gate = cal["gate_methods_cluster_median"]
    field = cal.get("published_field_median")
    panels = load_panels(a.reviews)
    if not panels:
        print(f"ERROR: no panel*/R*.json found under {a.reviews}", file=sys.stderr)
        return 2
    comp, npan = composite(panels, mu, sd, metrics)
    if comp is None:
        print("ERROR: could not compute composite (no valid channels)", file=sys.stderr)
        return 2
    passed = comp >= gate
    # per-metric mean (diagnostic) + calibration_honesty/rigor watch
    permetric = {}
    for metric in metrics:
        vals = [r["metrics"][metric]["score"] for rows in panels.values() for r in rows.values()
                if metric in r.get("metrics", {})]
        if vals: permetric[metric] = round(statistics.mean(vals), 3)
    out = {"label": a.label, "panels": npan, "composite": round(comp, 4),
           "gate": gate, "passed": passed, "margin_vs_gate": round(comp - gate, 4),
           "field_median": field, "per_metric_mean": permetric,
           "calibration_honesty": permetric.get("calibration_honesty"),
           "rigor": permetric.get("rigor")}
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"[{a.label}] composite={comp:+.4f}  gate={gate:+.4f}  "
              f"{'PASS' if passed else 'FAIL'} (margin {comp-gate:+.4f}); "
              f"panels={npan}; calib_honesty={permetric.get('calibration_honesty')} "
              f"rigor={permetric.get('rigor')}")
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())

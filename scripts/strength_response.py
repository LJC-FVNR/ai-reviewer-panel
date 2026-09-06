#!/usr/bin/env python3
"""strength_response.py -- does each transform's effect scale with how much of the paper it edited?

A negative mean delta is compatible with two stories. Either the edit did it, in which case a paper
edited in 55 places should move further than one edited in 21; or something about the variant arm did
it -- a later scoring session, a different queue position, an artefact of how the variants were built
-- in which case the size of the edit is irrelevant and the correlation is noise. The drift control
(run_n3.sh) rules out the session; this rules in the dose.

The test is Spearman rho between the per-paper edit count that pia_transforms.py recorded when it built
the variant and the per-paper delta the panel returned, computed on both rosters. Each roster is read over
its own declared set of papers, taken from that roster's own input directory rather than from the other's,
because the two sets are neither equal nor nested: the five-model arm covers every accepted paper and the
vendor arm covers the eight it was run on. n is small on either roster and the CI will say so; the point is
the sign and whether the two rosters agree, not a p-value.

WHAT WOULD MAKE THIS UNINTERPRETABLE. Edit count is confounded with paper length -- a longer paper
offers more sentences to join -- so a raw correlation could be reading length rather than dose. So the
edit count is also expressed per 1000 baseline words and the correlation reported both ways. If the
two disagree, the raw one is reading length and the normalised one is the answer.

Reports; writes strength_response.json. Nothing here feeds a claim in the body -- it is an appendix
check that the body's negative deltas are dose-dependent.
"""
import glob
import json
import os
import random
import statistics as st

WS = "/path/to/workspace"
CAL = f"{WS}/paper_direction_98_calibration"
HERE = f"{WS}/ai_native_academia"
PARAMS5 = f"{CAL}/ICLR/calibration_params_portable.json"
PARAMS8 = f"{HERE}/n0_cursor8_iclr/calibration_params_cursor8_iclr.json"
BASE5 = f"{CAL}/reviews"
VAR5 = f"{HERE}/n1_pia_5model/reviews"
BASE8 = f"{HERE}/n0_cursor8_iclr/reviews"
VAR8 = f"{HERE}/n2_pia_cursor8/reviews"
MANIFEST = f"{HERE}/pia_variants/manifest.json"
ARMS = ["T1_endmatter", "T2_concede", "T3_lengthen"]
SEED = 20260830


def load_params(path):
    p = json.load(open(path))
    return p["mu"], p["sd"], p["metrics"]


def composite(rev_dir, mu, sd, metrics, glob_pat):
    """Mean z over (slot, metric) channels within a panel, then over panels.

    Copied from analyse_n1.composite rather than imported, because the slot filename pattern differs
    between rosters (R*.json vs C*.json) and analyse_n1 hardcodes its own. Same arithmetic.
    """
    per_panel = []
    for pdir in sorted(glob.glob(os.path.join(rev_dir, "panel*"))):
        zs = []
        for f in sorted(glob.glob(os.path.join(pdir, glob_pat))):
            slot = os.path.basename(f)[:-5]
            try:
                rev = json.load(open(f))
            except Exception:
                continue
            for m in metrics:
                key = f"{slot}|{m}"
                md = rev.get("metrics", {}).get(m)
                if key in mu and md and isinstance(md.get("score"), (int, float)):
                    zs.append((md["score"] - mu[key]) / sd[key])
        if zs:
            per_panel.append(st.mean(zs))
    return st.mean(per_panel) if per_panel else None


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def boot_ci(xs, ys, n=5000):
    rng = random.Random(SEED)
    k = len(xs)
    out = []
    for _ in range(n):
        idx = [rng.randrange(k) for _ in range(k)]
        bx, by = [xs[i] for i in idx], [ys[i] for i in idx]
        if len(set(bx)) > 1 and len(set(by)) > 1:
            out.append(spearman(bx, by))
    out.sort()
    if not out:
        return None, None
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def arm(roster, params, base_root, var_root, pat, papers, manifest, var_layout):
    """var_layout: the two runners wrote different trees -- run_n1.sh one dir per paper-variant unit,
    run_n2.sh a variant dir nested under the paper. Neither is wrong and neither is worth rewriting
    after the reviews are spent, so the path is a parameter."""
    mu, sd, metrics = load_params(params)
    dropped = {(e["paper"], e["transform"]) for e in manifest.get("excluded", [])}
    rows = {}
    for a in ARMS:
        xs_raw, xs_norm, ys, per = [], [], [], []
        for p in papers:
            b = composite(os.path.join(base_root, p), mu, sd, metrics, pat)
            v = composite(os.path.join(var_root, var_layout.format(paper=p, arm=a)),
                          mu, sd, metrics, pat)
            if b is None or v is None:
                # Two different things land here and they must not print the same way. A cell the variant
                # gate dropped below its pre-registered strength floor is absent by rule, and dropping it
                # from a dose-response correlation removes a point at the bottom of the dose axis, which
                # weakens this statistic rather than flattering it. Anything else is a hole in the scoring
                # and has to be filled before this number is read.
                #
                # `papers` is the roster's own declared scope, so a paper the other roster covers is not a
                # hole here: the two rosters were run over different sets, and an unscored cell outside a
                # roster's scope was never asked for. Reading one roster's absences off the other roster's
                # paper list printed two dozen phantom holes when the five-model set grew and this one did not.
                why = ("excluded by the variant gate: below its pre-registered strength floor"
                       if (p, a) in dropped else "MISSING -- a hole in the scoring, not an exclusion")
                print(f"  {roster} {a} {p}: {why}")
                continue
            e = manifest["variants"][p][a]["edits"]
            w = manifest["variants"][p]["baseline"]["words"]
            xs_raw.append(e)
            xs_norm.append(1000.0 * e / w)
            ys.append(v - b)
            per.append({"paper": p, "edits": e, "edits_per_kword": round(1000.0 * e / w, 3),
                        "delta": round(v - b, 4)})
        rho = spearman(xs_raw, ys)
        lo, hi = boot_ci(xs_raw, ys)
        rho_n = spearman(xs_norm, ys)
        lo_n, hi_n = boot_ci(xs_norm, ys)
        rows[a] = {
            "n": len(ys),
            "n_excluded_by_gate": sum(1 for pp, aa in dropped if aa == a and pp in papers),
            "n_holes": (len(papers) - len(ys)
                        - sum(1 for pp, aa in dropped if aa == a and pp in papers)),
            "scope": len(papers),
            "edits": {"min": min(xs_raw), "median": st.median(xs_raw), "max": max(xs_raw)},
            "median_delta": round(st.median(ys), 4),
            # A negative rho means more editing -> a lower score, i.e. the effect is dose-dependent.
            "rho_edits_vs_delta": round(rho, 4),
            "rho_ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
            "rho_edits_per_kword_vs_delta": round(rho_n, 4),
            "rho_per_kword_ci95": [None if lo_n is None else round(lo_n, 4),
                                   None if hi_n is None else round(hi_n, 4)],
            "per_paper": sorted(per, key=lambda r: r["edits"]),
        }
        print(f"  {roster:8} {a:14} n={len(ys)} edits {min(xs_raw)}-{max(xs_raw)} "
              f"med Delta {st.median(ys):+.4f}  rho={rho:+.3f} [{lo:+.3f},{hi:+.3f}]  "
              f"per-kword rho={rho_n:+.3f}")
    return rows


def main():
    manifest = json.load(open(MANIFEST))
    papers = manifest["papers"]
    # The vendor roster's scope is the set of papers its own run was given, read off that run's input
    # directory. Deriving it rather than repeating the number keeps the two arms from being described by
    # one count that is only ever right for one of them.
    papers8 = sorted(os.listdir(os.path.join(os.path.dirname(VAR8), "inputs")))
    print(f"strength-response over {len(ARMS)} arms: {len(papers)} papers on the five-model roster, "
          f"{len(papers8)} on the vendor roster ({len(set(papers) & set(papers8))} in common)")
    out = {
        "papers": papers,
        "papers_cursor8": papers8,
        "note": ("Spearman rho between the per-paper edit count pia_transforms.py recorded and the "
                 "per-paper delta the panel returned. Negative rho = dose-dependent: the more of the "
                 "paper the transform touched, the further the score fell. n is small on either "
                 "roster, so the CI is wide by construction; the reportable facts are the sign and "
                 "whether the rosters agree."),
        "five_model": arm("5-model", PARAMS5, BASE5, VAR5, "R*.json", papers, manifest,
                          "{paper}__{arm}"),
        "cursor8": arm("cursor8", PARAMS8, BASE8, VAR8, "C*.json", papers8, manifest,
                       os.path.join("{paper}", "{arm}")),
    }
    agree = {a: (out["five_model"][a]["rho_edits_vs_delta"] < 0)
                == (out["cursor8"][a]["rho_edits_vs_delta"] < 0) for a in ARMS}
    out["rosters_agree_on_sign"] = agree
    print("\nrosters agree on the sign of rho: " +
          ", ".join(f"{a.split('_')[0]} {'yes' if v else 'NO'}" for a, v in agree.items()))
    json.dump(out, open(f"{HERE}/strength_response.json", "w"), indent=2)
    print(f"wrote {HERE}/strength_response.json")


if __name__ == "__main__":
    main()

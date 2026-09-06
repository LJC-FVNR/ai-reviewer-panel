#!/usr/bin/env python3
"""Analysis for the discrimination study.

Composite is defined exactly as in ICLR/score_against_gate.py: for each (slot, metric)
channel, z = (score - mu)/sd against the calibration built from the 16 already-accepted
ICLR-2026 papers; average over channels within a panel, then over panels. So a composite
of 0 means "indistinguishable from the average already-accepted paper on this instrument".

Three questions, in decreasing order of how much the design can support:

  Q1 (clean)      Within the rejected arm -- one venue, one primary area, one submission
                  stage, one artifact pipeline, no label cue -- does the panel rank papers
                  the way the venue's own reviewers did? Reported as Spearman rho against
                  final post-rebuttal human mean rating and as the low-vs-high contrast.
  Q2 (clean)      Where do rejected papers fall relative to the accepted calibration band,
                  in units of the panel's own test-retest noise?
  Q3 (confounded) Accepted vs rejected AUC. The accepted arm is preprint-stage arXiv text
                  and the rejected arm is as-submitted OpenReview text, so this number is
                  an upper bound, not an estimate. Reported with that caveat attached.
"""
import glob
import json
import os
import statistics as st

import numpy as np
from scipy import stats

CAL = "/path/to/workspace/paper_direction_98_calibration"
CALIB = json.load(open(f"{CAL}/ICLR/calibration_params_portable.json"))
MU, SD, METRICS = CALIB["mu"], CALIB["sd"], CALIB["metrics"]
GATE = CALIB["gate_methods_cluster_median"]
SLOTS = ["R1", "R2", "R3", "R4", "R5"]
GRADE_ORDER = ["Reject", "Reject and Resubmit", "Major Revision", "Minor Revision", "Accept"]


def paper_scores(rev_dir):
    """-> (composite, n_panels, n_reviews, grades, per_metric_means, scored_at)"""
    panel_means, grades, per_metric, mtimes, panels = [], [], {}, [], []
    for pdir in sorted(glob.glob(os.path.join(rev_dir, "panel*"))):
        zs, pt = [], []
        for slot in SLOTS:
            f = os.path.join(pdir, f"{slot}.json")
            if not os.path.exists(f):
                continue
            mtimes.append(os.path.getmtime(f))
            pt.append(os.path.getmtime(f))
            try:
                rev = json.load(open(f))
            except Exception:
                continue
            grades.append(rev.get("grade"))
            m = rev.get("metrics", {})
            for metric in METRICS:
                key = f"{slot}|{metric}"
                if metric in m and key in MU and SD.get(key):
                    zs.append((m[metric]["score"] - MU[key]) / SD[key])
                    per_metric.setdefault(metric, []).append(m[metric]["score"])
        if zs:
            panel_means.append(st.mean(zs))
            panels.append(dict(panel=os.path.basename(pdir), mean=st.mean(zs),
                               t=st.median(pt) if pt else None))
    comp = st.mean(panel_means) if panel_means else None
    return (comp, len(panel_means), len(grades), grades,
            {k: st.mean(v) for k, v in per_metric.items()},
            st.median(mtimes) if mtimes else None, panels)


def auc(pos, neg):
    """P(a random pos scores above a random neg), ties at 0.5."""
    n = 0.0
    for a in pos:
        for b in neg:
            n += 1.0 if a > b else 0.5 if a == b else 0.0
    return n / (len(pos) * len(neg))


def boot_ci(fn, *args, n=4000, seed=0, paired=False):
    """Bootstrap CI. `paired=True` resamples one index vector shared by all arguments.

    The distinction is not cosmetic. A two-sample statistic like AUC(pos, neg) draws its
    arms independently, which is what the default does. A *paired* statistic like
    Spearman(composite, human_rating) is a property of the pairing, and resampling each
    vector with its own index draw destroys exactly that -- it returns a CI centred on
    zero regardless of the true association. This version of the code reported
    rho=+0.595 with 95% CI [-0.348, +0.360], a CI that does not contain its own point
    estimate: the tell that the pairing was being shuffled.
    """
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        if paired:
            idx = rng.integers(0, len(args[0]), len(args[0]))
            rs = [list(np.array(a)[idx]) for a in args]
        else:
            rs = [list(np.array(a)[rng.integers(0, len(a), len(a))]) for a in args]
        try:
            out.append(fn(*rs))
        except Exception:
            pass
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if out else (None, None)


def partial_spearman(y, x, z):
    """Spearman(y, x) holding z fixed, via rank residuals."""
    ry, rx, rz = (np.asarray(stats.rankdata(v), dtype=float) for v in (y, x, z))

    def resid(v):
        b = np.polyfit(rz, v, 1)
        return v - (b[0] * rz + b[1])

    r, p = stats.spearmanr(resid(ry), resid(rx))
    return float(r), float(p)


sample = {p["forum"]: p for p in json.load(open("sample_preregistered.json"))["papers"]}
rows = []
for d in sorted(glob.glob("reviews/*")):
    eid = os.path.basename(d)
    arm, forum = eid.split("_", 1)
    comp, npan, nrev, grades, pm, tsc, panels = paper_scores(d)
    if comp is None or nrev < 10:
        print(f"  (incomplete: {eid} {nrev}/10 reviews)")
        continue
    p = sample[forum]
    rows.append(dict(forum=forum, arm=arm, composite=comp, n_reviews=nrev, n_panels=npan,
                     grades=grades, human=p["rating_mean"], human_max=p["rating_max"],
                     nrev_human=p["nrev"], per_metric=pm, title=p["title"], scored_at=tsc,
                     panels=panels))

# ---- accepted reference arm (defines mu/sd; its mean is ~0 by construction)
ref = []
for d in sorted(glob.glob(f"{CAL}/reviews/*")):
    comp, npan, nrev, grades, pm, tsc, panels = paper_scores(d)
    if comp is not None and nrev >= 10:
        ref.append(dict(eid=os.path.basename(d), composite=comp, grades=grades, n_reviews=nrev))

print(f"\n{'='*78}\nREJECTED ARM: {len(rows)} papers scored "
      f"({sum(r['n_reviews'] for r in rows)} reviews)")
print(f"ACCEPTED REFERENCE: {len(ref)} papers ({sum(r['n_reviews'] for r in ref)} reviews)\n")

# Publication labels. These 32 papers are third-party rejected submissions, and the paper's
# ethical position is that every manuscript it *attacks* is our own. Scoring someone else's
# rejected submission and printing a resolvable OpenReview forum id next to "lowest of 32"
# publishes a claim about identifiable authors who never consented to it -- and it is the
# same disclosure the paper's own §8 tells venues not to make. So the released table carries
# arm-blind labels R01..R32 keyed off a hash of the forum id (see public_labels.json), the
# forum ids stay local, and the mapping is not released.
PUB = json.load(open("public_labels.json")) if os.path.exists("public_labels.json") else {}
LOCAL = os.environ.get("SHOW_FORUM_IDS") == "1"
label = (lambda f: f) if LOCAL else (lambda f: PUB.get(f, "R??"))
if not LOCAL:
    print("  (paper column shows release labels; SHOW_FORUM_IDS=1 for local forum ids)")

print(f"{'paper':<14}{'arm':<6}{'human':>7}{'composite':>11}{'grades (10 reviewers)':>24}")
for r in sorted(rows, key=lambda r: -r["composite"]):
    g = "/".join(f"{sum(1 for x in r['grades'] if x == k)}" for k in GRADE_ORDER)
    print(f"{label(r['forum']):<14}{r['arm']:<6}{r['human']:>7.2f}{r['composite']:>11.4f}   {g:>18}")
print(f"   grade columns: {' / '.join(GRADE_ORDER)}")

low = [r["composite"] for r in rows if r["arm"] == "low"]
high = [r["composite"] for r in rows if r["arm"] == "high"]
out = dict(n_rejected=len(rows), n_reviews=sum(r["n_reviews"] for r in rows), papers=rows)

# ---- Q0: scoring-time audit. Scoring 320 reviews at 8-way concurrency spreads across
# hours (downloading no longer does -- see or_client.OR.pdf), so if scoring time is
# arm-correlated, any drift in model routing, load, or effort resolution shows up as an arm
# effect. Order is arm-balanced by construction now, but the first rounds ran low-arm-first,
# so the residue is measured here instead of asserted away.
if low and high and all(r.get("scored_at") for r in rows):
    t0 = min(r["scored_at"] for r in rows)
    for r in rows:
        r["scored_h"] = (r["scored_at"] - t0) / 3600.0
    print(f"\n{'='*78}\nQ0  scoring-time audit (validity precondition for Q1)")
    span = {}
    for arm in ("low", "high"):
        h = sorted(r["scored_h"] for r in rows if r["arm"] == arm)
        span[arm] = (h[0], h[-1])
        print(f"  {arm:<5} n={len(h):<3} scored at h={h[0]:.2f}..{h[-1]:.2f} "
              f"(mean {st.mean(h):.2f})")
    th = [r["scored_h"] for r in rows]
    tc = [r["composite"] for r in rows]
    trho, tp = stats.spearmanr(tc, th)
    print(f"  Spearman(composite, scoring hour) pooled: rho={trho:+.3f} (p={tp:.4f})")
    # Within-arm drift, holding human rating fixed. The raw within-arm correlation is NOT
    # a clean drift test here: the pre-registered sample file is sorted by
    # |rating - target| (select_sample.py), so the low arm is stored 2.00 x11 then
    # 2.40/2.40/2.50/2.50/2.50, and the early arm-blocked rounds scored it in that order.
    # Scoring time is therefore correlated with human rating by construction of the
    # selection rule, and composite tracks human rating -- that is the finding. Partialling
    # out rating separates instrument drift from the selection sort.
    within, within_partial = {}, {}
    for arm in ("low", "high"):
        a = [r for r in rows if r["arm"] == arm]
        if len(a) >= 4:
            wr, wp = stats.spearmanr([r["composite"] for r in a], [r["scored_h"] for r in a])
            within[arm] = (float(wr), float(wp))
            line = f"  within {arm:<5}: raw rho={wr:+.3f} (p={wp:.4f})"
            if len(set(r["human"] for r in a)) > 1:
                pr, pp = partial_spearman([r["composite"] for r in a],
                                          [r["scored_h"] for r in a],
                                          [r["human"] for r in a])
                within_partial[arm] = (pr, pp)
                line += f"   | human rating: rho={pr:+.3f} (p={pp:.4f})"
            print(line)
    print("  (the partialled column is the drift test; the raw one is contaminated by the "
          "selection sort)")
    # Decisive drift test: within paper. Every paper is scored by two panels at different
    # wall-clock times on the *identical* manuscript, so differencing the two panels removes
    # paper quality, length, arm and selection order exactly. Only instrument drift can
    # produce a correlation between the panel gap in score and the panel gap in time. This
    # is why the raw and partialled within-arm columns above disagree in sign: with n=16 per
    # arm they are estimating a small effect through two confounds, and this test is not.
    dt, dc = [], []
    for r in rows:
        ps = [q for q in r.get("panels", []) if q.get("t") is not None]
        if len(ps) == 2:
            ps.sort(key=lambda q: q["t"])
            dt.append((ps[1]["t"] - ps[0]["t"]) / 3600.0)
            dc.append(ps[1]["mean"] - ps[0]["mean"])
    if len(dt) >= 8:
        drho, dp = stats.spearmanr(dc, dt)
        wil = stats.wilcoxon(dc)
        print(f"  within-paper (n={len(dt)} papers, two panels each): "
              f"Spearman(panel score gap, panel time gap) rho={drho:+.3f} (p={dp:.4f})")
        print(f"    later panel minus earlier: mean {st.mean(dc):+.4f} z, "
              f"median {st.median(dc):+.4f} z, Wilcoxon p={wil.pvalue:.4f}  "
              f"(paper identity differenced out)")
        out.setdefault("q0_within_paper", dict(
            n=len(dt), rho=float(drho), p=float(dp), mean_gap=st.mean(dc),
            median_gap=st.median(dc), wilcoxon_p=float(wil.pvalue),
            mean_hours_between_panels=st.mean(dt)))

    w0 = max(span["low"][0], span["high"][0])
    w1 = min(span["low"][1], span["high"][1])
    wl = [r["composite"] for r in rows if r["arm"] == "low" and w0 <= r["scored_h"] <= w1]
    wh = [r["composite"] for r in rows if r["arm"] == "high" and w0 <= r["scored_h"] <= w1]
    ov = None
    if len(wl) >= 3 and len(wh) >= 3:
        ov = dict(window=[w0, w1], n_low=len(wl), n_high=len(wh),
                  gap=st.mean(wh) - st.mean(wl), auc=auc(wh, wl))
        print(f"  overlap window h={w0:.2f}..{w1:.2f}: low n={len(wl)} {st.mean(wl):+.4f}  "
              f"high n={len(wh)} {st.mean(wh):+.4f}  gap {ov['gap']:+.4f} z  "
              f"AUC {ov['auc']:.3f}")
        print("  (if this gap tracks the full-sample gap, scoring time is not driving it)")
    else:
        print(f"  overlap window h={w0:.2f}..{w1:.2f} holds too few papers "
              f"(low {len(wl)}, high {len(wh)}) to re-test the gap")
    out["q0"] = dict(pooled_rho=float(trho), pooled_p=float(tp), within=within,
                     within_partial=within_partial,
                     arm_span={k: list(v) for k, v in span.items()}, overlap=ov)

# ---- Q0b: length audit. The high arm's papers are physically longer (source page count
# 23.7 vs 18.5), which is intrinsic to the quality contrast rather than an artifact --
# better-reviewed papers carry more experiments and appendices -- but length rank-correlates
# with composite at rho=+0.24 in the reference set, so part of any gap could be length
# rather than content. Reported as a partial correlation and as a length-overlap re-test,
# not adjusted away.
DEIDX = "deid_index.json"
if low and high and os.path.exists(DEIDX):
    dx = json.load(open(DEIDX))
    for r in rows:
        r["words"] = (dx.get(r["forum"]) or {}).get("deid_words")
        r["src_pages"] = (dx.get(r["forum"]) or {}).get("src_pages")
    L = [r for r in rows if r.get("words")]
    if len(L) >= 8:
        print(f"\n{'='*78}\nQ0b length audit (composite vs manuscript length)")
        for arm in ("low", "high"):
            w = [r["words"] for r in L if r["arm"] == arm]
            pg = [r["src_pages"] for r in L if r["arm"] == arm and r["src_pages"]]
            print(f"  {arm:<5} n={len(w):<3} de-id words mean={st.mean(w):.0f}"
                  + (f"   source pages mean={st.mean(pg):.1f}" if pg else ""))
        cw = [r["composite"] for r in L]
        ww = [r["words"] for r in L]
        hh2 = [r["human"] for r in L]
        lrho, lp = stats.spearmanr(cw, ww)
        print(f"  Spearman(composite, de-id words) pooled: rho={lrho:+.3f} (p={lp:.4f})")
        hrho, hp = stats.spearmanr(hh2, ww)
        print(f"  Spearman(human rating, de-id words) pooled:  rho={hrho:+.3f} (p={hp:.4f})"
              f"   -- humans reward length too, so length is partly signal, not only artifact")
        prho, pp = partial_spearman(cw, hh2, ww)
        wrho, wp2 = partial_spearman(cw, ww, hh2)
        print(f"  partial Spearman(composite, human | length) over n={len(L)}: "
              f"rho={prho:+.3f} (p={pp:.4f})")
        print(f"  partial Spearman(composite, length | human) over n={len(L)}: "
              f"rho={wrho:+.3f} (p={wp2:.4f})   -- what length adds beyond human-judged quality")
        # re-test the gap on the length band both arms occupy
        lo_w = sorted(r["words"] for r in L if r["arm"] == "low")
        hi_w = sorted(r["words"] for r in L if r["arm"] == "high")
        b0, b1 = max(lo_w[0], hi_w[0]), min(lo_w[-1], hi_w[-1])
        bl = [r["composite"] for r in L if r["arm"] == "low" and b0 <= r["words"] <= b1]
        bh = [r["composite"] for r in L if r["arm"] == "high" and b0 <= r["words"] <= b1]
        lov = None
        if len(bl) >= 3 and len(bh) >= 3:
            lov = dict(band=[b0, b1], n_low=len(bl), n_high=len(bh),
                       gap=st.mean(bh) - st.mean(bl), auc=auc(bh, bl))
            print(f"  length band {b0}-{b1} words: low n={len(bl)} {st.mean(bl):+.4f}  "
                  f"high n={len(bh)} {st.mean(bh):+.4f}  gap {lov['gap']:+.4f} z  "
                  f"AUC {lov['auc']:.3f}")
        out["q0b"] = dict(length_rho=float(lrho), length_p=float(lp),
                          human_length_rho=float(hrho), human_length_p=float(hp),
                          partial_rho=float(prho), partial_p=float(pp),
                          partial_length_rho=float(wrho), partial_length_p=float(wp2),
                          length_band=lov,
                          words={a: st.mean([r["words"] for r in L if r["arm"] == a])
                                 for a in ("low", "high")})

if low and high:
    print(f"\n{'='*78}\nQ1  low vs high within the rejected arm (clean contrast)")
    hl = [r["human"] for r in rows if r["arm"] == "low"]
    hh = [r["human"] for r in rows if r["arm"] == "high"]
    print(f"  human rating   low {st.mean(hl):+.3f}   high {st.mean(hh):+.3f}   "
          f"gap {st.mean(hh)-st.mean(hl):+.3f} points")
    print(f"  panel composite low {st.mean(low):+.4f} (sd {st.pstdev(low):.3f})   "
          f"high {st.mean(high):+.4f} (sd {st.pstdev(high):.3f})   "
          f"gap {st.mean(high)-st.mean(low):+.4f} z")
    u = stats.mannwhitneyu(high, low, alternative="two-sided")
    a = auc(high, low)
    lo, hi = boot_ci(auc, high, low)
    print(f"  Mann-Whitney U={u.statistic:.1f}  p={u.pvalue:.4f}")
    print(f"  AUC(high>low)={a:.3f}  95% CI [{lo:.3f}, {hi:.3f}]   "
          f"Cliff's delta={2*a-1:+.3f}")
    d = (st.mean(high)-st.mean(low)) / st.pstdev(low+high) if st.pstdev(low+high) else 0
    print(f"  Cohen's d={d:+.3f}")
    out.update(q1=dict(low_mean=st.mean(low), high_mean=st.mean(high),
                       gap=st.mean(high)-st.mean(low), auc=a, auc_ci=[lo, hi],
                       mw_p=float(u.pvalue), cohens_d=d,
                       human_gap=st.mean(hh)-st.mean(hl)))

    hum = [r["human"] for r in rows]
    comp = [r["composite"] for r in rows]
    rho, prho = stats.spearmanr(comp, hum)
    tau, ptau = stats.kendalltau(comp, hum)
    rlo, rhi = boot_ci(lambda a, b: stats.spearmanr(a, b)[0], comp, hum, paired=True)
    print(f"\n  Spearman(panel composite, human mean rating) over n={len(rows)}: "
          f"rho={rho:+.3f} (p={prho:.4f}, 95% CI [{rlo:+.3f}, {rhi:+.3f}])")
    print(f"  Kendall tau={tau:+.3f} (p={ptau:.4f})")
    out["q1"].update(spearman=float(rho), spearman_p=float(prho), spearman_ci=[rlo, rhi],
                     kendall=float(tau), kendall_p=float(ptau))

if ref and rows:
    rc = [r["composite"] for r in ref]
    allrej = [r["composite"] for r in rows]
    print(f"\n{'='*78}\nQ2  rejected papers against the accepted calibration band")
    print(f"  accepted (n={len(rc)}):  mean {st.mean(rc):+.4f}  median {st.median(rc):+.4f}  "
          f"range [{min(rc):+.4f}, {max(rc):+.4f}]")
    print(f"  rejected (n={len(allrej)}): mean {st.mean(allrej):+.4f}  "
          f"median {st.median(allrej):+.4f}  range [{min(allrej):+.4f}, {max(allrej):+.4f}]")
    print(f"  gate (accepted methods-cluster median) = {GATE:+.4f}; "
          f"rejected papers clearing it: {sum(1 for x in allrej if x >= GATE)}/{len(allrej)}")
    print(f"\n{'='*78}\nQ3  accepted vs rejected (CONFOUNDED: preprint arXiv text vs "
          f"as-submitted OpenReview text)")
    a3 = auc(rc, allrej)
    l3, h3 = boot_ci(auc, rc, allrej)
    print(f"  AUC(accepted>rejected)={a3:.3f}  95% CI [{l3:.3f}, {h3:.3f}]  "
          f"-- upper bound only")
    out.update(q2=dict(accepted_mean=st.mean(rc), accepted_median=st.median(rc),
                       rejected_mean=st.mean(allrej), rejected_median=st.median(allrej),
                       gate=GATE, rejected_clearing_gate=sum(1 for x in allrej if x >= GATE)),
               q3=dict(auc=a3, auc_ci=[l3, h3], caveat="stage/source confounded upper bound"))

elif ref:
    rc = [r["composite"] for r in ref]
    print(f"\n  accepted reference band (n={len(rc)}): mean {st.mean(rc):+.4f} "
          f"median {st.median(rc):+.4f} range [{min(rc):+.4f}, {max(rc):+.4f}]; gate {GATE:+.4f}")

print(f"\n{'='*78}\nGRADES")
for tag, g in (("rejected-low", [x for r in rows if r["arm"] == "low" for x in r["grades"]]),
               ("rejected-high", [x for r in rows if r["arm"] == "high" for x in r["grades"]]),
               ("accepted ref", [x for r in ref for x in r["grades"]])):
    if not g:
        continue
    c = {k: g.count(k) for k in GRADE_ORDER}
    print(f"  {tag:<15} n={len(g):<4} " +
          "  ".join(f"{k}={c[k]} ({100*c[k]/len(g):.0f}%)" for k in GRADE_ORDER))
out["grades"] = {tag: {k: g.count(k) for k in GRADE_ORDER} for tag, g in
                 (("rejected_low", [x for r in rows if r["arm"] == "low" for x in r["grades"]]),
                  ("rejected_high", [x for r in rows if r["arm"] == "high" for x in r["grades"]]),
                  ("accepted_ref", [x for r in ref for x in r["grades"]]))}
json.dump(out, open("analysis_results.json", "w"), indent=1, default=float)
print("\nwrote analysis_results.json")

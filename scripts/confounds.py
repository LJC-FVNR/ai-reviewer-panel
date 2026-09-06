#!/usr/bin/env python3
"""Robustness of the discrimination result to the panel roster, on ICLR data.

A roster-robustness check has to be run on the population the claim is about, and on a quantity that has
something to be right or wrong against. Asking instead whether some one manuscript keeps its rank when a
reviewer is dropped answers nothing: an unlabelled manuscript has no outcome to agree with, so its rank can
be stable under every roster while the panel's agreement with human decisions is carried by a single slot.

The question worth asking is whether the paper's *claim* is roster-dependent: the claim is that the
panel ranks, evidenced by rho(composite, human post-rebuttal mean) = +0.595 and AUC(high>low) = 0.820
over 32 rejected ICLR-2026 papers. If one lenient or one unusually discerning slot carries that, the
result is a property of a model, not of a panel. Two views:

  drop-one    recompute the composite from the other four slots, then re-run rho and AUC. Five fits.
              If the claim is a panel property, all five stay close to the full-panel value.
  slot-alone  each slot's own single-model composite, scored the same way. Not a robustness check but
              the more informative one: it says whether a panel is buying anything over one reviewer.

Composite is defined exactly as in reject_arm/analyze.py -- z against the accepted-16 calibration
per (slot, metric) channel, averaged over channels within a panel, then over panels -- with the slot
set restricted. Restricting slots does not require recalibration, because mu/sd are per-channel.
"""
import glob
import json
import os
import statistics as st

import numpy as np
from scipy import stats

WS = "/path/to/workspace"
CAL = f"{WS}/paper_direction_98_calibration"
CALIB = json.load(open(f"{CAL}/ICLR/calibration_params_portable.json"))
MU, SD, METRICS = CALIB["mu"], CALIB["sd"], CALIB["metrics"]
ALL_SLOTS = ["R1", "R2", "R3", "R4", "R5"]
REJ = f"{WS}/ai_native_academia/reject_arm"
PUB = json.load(open(f"{REJ}/public_labels.json"))
HUMAN = {r["forum"]: r for r in json.load(open(f"{REJ}/sample_preregistered.json"))["papers"]} \
    if os.path.exists(f"{REJ}/sample_preregistered.json") else {}


def composite(rev_dir, slots):
    """Mean z over (slot, metric) channels within a panel, then over panels. None if no channel."""
    panel_means = []
    for pdir in sorted(glob.glob(os.path.join(rev_dir, "panel*"))):
        zs = []
        for slot in slots:
            f = os.path.join(pdir, f"{slot}.json")
            if not os.path.exists(f) or os.path.getsize(f) < 2:
                continue
            try:
                m = json.load(open(f)).get("metrics", {})
            except Exception:
                continue
            for metric in METRICS:
                key = f"{slot}|{metric}"
                if metric in m and key in MU and SD.get(key):
                    zs.append((m[metric]["score"] - MU[key]) / SD[key])
        if zs:
            panel_means.append(st.mean(zs))
    return st.mean(panel_means) if panel_means else None


def load_arms():
    """-> list of (forum, arm, human_mean). Arm comes from the directory prefix, the authority."""
    rows = []
    for d in sorted(glob.glob(f"{REJ}/reviews/*")):
        name = os.path.basename(d)
        arm, _, forum = name.partition("_")
        if arm not in ("low", "high"):
            continue
        # `rating_mean` is the post-rebuttal final mean, and is the exact key analyze.py
        # correlates against (analyze.py:127). Do not substitute a different rating field.
        rows.append((forum, arm, HUMAN.get(forum, {}).get("rating_mean")))
    return rows


ARMS = load_arms()
print(f"papers: {len(ARMS)}  low={sum(1 for r in ARMS if r[1]=='low')}  "
      f"high={sum(1 for r in ARMS if r[1]=='high')}  with human rating="
      f"{sum(1 for r in ARMS if r[2] is not None)}")


def evaluate(slots):
    comps, hums, lo, hi = [], [], [], []
    for forum, arm, human in ARMS:
        c = composite(f"{REJ}/reviews/{arm}_{forum}", slots)
        if c is None:
            continue
        (lo if arm == "low" else hi).append(c)
        if human is not None:
            comps.append(c)
            hums.append(human)
    rho, p = stats.spearmanr(comps, hums)
    # AUC = P(high > low) with ties at 0.5, i.e. the Mann-Whitney U statistic normalised
    u = sum((1.0 if b > a else 0.5 if b == a else 0.0) for a in lo for b in hi)
    return dict(n=len(comps), rho=rho, p=p, auc=u / (len(lo) * len(hi)),
                gap=st.mean(hi) - st.mean(lo), mean=st.mean(lo + hi))


full = evaluate(ALL_SLOTS)
print(f"\nfull panel (5 slots)   n={full['n']}  rho={full['rho']:+.3f} (p={full['p']:.4f})  "
      f"AUC={full['auc']:.3f}  gap={full['gap']:+.3f} z  mean={full['mean']:+.3f} z")

print("\ndrop-one-slot  (composite from the other four; is the claim roster-dependent?)")
rows = []
for drop in ALL_SLOTS:
    r = evaluate([s for s in ALL_SLOTS if s != drop])
    rows.append((drop, r))
    print(f"  without {drop}:  rho={r['rho']:+.3f} (p={r['p']:.4f})  AUC={r['auc']:.3f}  "
          f"gap={r['gap']:+.3f} z   drho={r['rho']-full['rho']:+.3f}  dAUC={r['auc']-full['auc']:+.3f}")
rhos = [r["rho"] for _, r in rows]
aucs = [r["auc"] for _, r in rows]
print(f"  range: rho [{min(rhos):+.3f}, {max(rhos):+.3f}]   AUC [{min(aucs):.3f}, {max(aucs):.3f}]")

print("\nslot-alone  (one model, scored identically; does the panel buy anything?)")
solo = []
for s in ALL_SLOTS:
    r = evaluate([s])
    solo.append((s, r))
    print(f"  {s} only:     rho={r['rho']:+.3f} (p={r['p']:.4f})  AUC={r['auc']:.3f}  "
          f"gap={r['gap']:+.3f} z  mean={r['mean']:+.3f} z")
srho = [r["rho"] for _, r in solo]
sauc = [r["auc"] for _, r in solo]
print(f"  range: rho [{min(srho):+.3f}, {max(srho):+.3f}]   AUC [{min(sauc):.3f}, {max(sauc):.3f}]")
print(f"  best single slot rho={max(srho):+.3f} vs full panel {full['rho']:+.3f}  "
      f"(panel - best solo = {full['rho']-max(srho):+.3f})")
print(f"  mean solo rho={st.mean(srho):+.3f}, mean solo AUC={st.mean(sauc):.3f}")

# "Aggregation buys no validity" is a NULL claim, so it does not get to rest on a point estimate.
# Paired bootstrap over papers: the same resampled papers score the panel and every solo slot, so
# the difference is within-paper and the shared paper-difficulty variance cancels. Note max-of-5 is
# upward-biased by selection, which is exactly why panel-minus-BEST is reported as a bound and the
# headline is stated against the MEAN slot.
def rho_for(slots, idx, cache={}):
    key = tuple(slots)
    if key not in cache:
        cache[key] = [(composite(f"{REJ}/reviews/{a}_{f}", slots), h)
                      for f, a, h in ARMS if h is not None]
    pts = [cache[key][i] for i in idx]
    return stats.spearmanr([c for c, _ in pts], [h for _, h in pts])[0]


n = sum(1 for r in ARMS if r[2] is not None)
rng = np.random.default_rng(20260830)
d_mean, d_best = [], []
# The loop already computes every slot's rho on every resample; keeping them costs nothing and gives
# each solo slot its own interval. F2 plots these: a null about aggregation must not be drawn as five
# bare points, or the picture asserts a precision the bootstrap never granted.
solo_boot: dict[str, list] = {x: [] for x in ALL_SLOTS}
panel_boot: list = []
for _ in range(5000):
    idx = rng.integers(0, n, n)
    if len({ARMS[i][2] for i in idx}) < 3:
        continue  # a degenerate resample cannot support a rank correlation
    p = rho_for(ALL_SLOTS, idx)
    s = [rho_for([x], idx) for x in ALL_SLOTS]
    for x, v in zip(ALL_SLOTS, s):
        solo_boot[x].append(v)
    panel_boot.append(p)
    d_mean.append(p - st.mean(s))
    d_best.append(p - max(s))


def ci(v):
    a = np.percentile(v, [2.5, 97.5])
    return f"{st.mean(v):+.3f}  95% CI [{a[0]:+.3f}, {a[1]:+.3f}]"


print(f"\npaired bootstrap, {len(d_mean)} resamples of {n} papers")
print(f"  panel rho - MEAN solo rho: {ci(d_mean)}   "
      f"P(panel>mean solo)={sum(x>0 for x in d_mean)/len(d_mean):.3f}")
print(f"  panel rho - BEST solo rho: {ci(d_best)}   "
      f"P(panel>best solo)={sum(x>0 for x in d_best)/len(d_best):.3f}")

# Does the discrimination claim hold on the population a venue actually decides on? The rejected arm
# spans a 3-point human gap by construction (extreme-group). The accepted 16 are homogeneous, which is
# the regime an accept/reject boundary lives in -- and 15 of them carry OpenReview ratings too, so the
# same instrument can be scored against human judgement on both. Unpaired bootstrap: different papers,
# so resample each population independently. n=15 is low-powered, and saying which of "lower" and
# "underpowered" produced a null is exactly what the CI is for.
ACC = json.load(open(f"{REJ}/criterion_validity_accepted_arm.json"))
ah, ac = [x["human"] for x in ACC], [x["composite"] for x in ACC]
ao = [x["panel_overall"] for x in ACC]
a_rho, a_p = stats.spearmanr(ac, ah)
o_rho, o_p = stats.spearmanr(ao, ah)
rej = [(composite(f"{REJ}/reviews/{a}_{f}", ALL_SLOTS), h) for f, a, h in ARMS if h is not None]
ba, br, bd = [], [], []
for _ in range(5000):
    i = rng.integers(0, len(ah), len(ah))
    j = rng.integers(0, len(rej), len(rej))
    if len({ah[k] for k in i}) < 3 or len({rej[k][1] for k in j}) < 3:
        continue
    x = stats.spearmanr([ac[k] for k in i], [ah[k] for k in i])[0]
    y = stats.spearmanr([rej[k][0] for k in j], [rej[k][1] for k in j])[0]
    ba.append(x)
    br.append(y)
    bd.append(y - x)
print(f"\ncriterion validity by population  ({len(ba)} unpaired resamples)")
print(f"  accepted 16 (homogeneous, n={len(ah)}, human sd {st.pstdev(ah):.2f}):  "
      f"rho={a_rho:+.3f} (p={a_p:.4f})  {ci(ba)}")
print(f"  rejected 32 (extreme-group, n={len(rej)}, human sd "
      f"{st.pstdev([h for _, h in rej]):.2f}):  rho={full['rho']:+.3f}  {ci(br)}")
print(f"  difference (rejected - accepted): {ci(bd)}   "
      f"P(rejected>accepted)={sum(x>0 for x in bd)/len(bd):.3f}")
print(f"  the human-legible channel is worse still: rho(panel overall_recommendation, human) "
      f"= {o_rho:+.3f} (p={o_p:.4f}) on the accepted arm")

json.dump(dict(full=full, drop_one={d: r for d, r in rows}, slot_alone={s: r for s, r in solo},
               validity_by_population=dict(
                   accepted_rho=a_rho, accepted_p=a_p, accepted_n=len(ah),
                   accepted_ci=list(np.percentile(ba, [2.5, 97.5])),
                   rejected_rho=full["rho"], rejected_ci=list(np.percentile(br, [2.5, 97.5])),
                   diff=st.mean(bd), diff_ci=list(np.percentile(bd, [2.5, 97.5])),
                   accepted_overall_rho=o_rho, accepted_overall_p=o_p),
               slot_alone_ci={x: list(np.percentile(v, [2.5, 97.5]))
                              for x, v in solo_boot.items()},
               panel_ci=list(np.percentile(panel_boot, [2.5, 97.5])),
               boot=dict(n_resamples=len(d_mean), d_mean_solo=st.mean(d_mean),
                         d_mean_solo_ci=list(np.percentile(d_mean, [2.5, 97.5])),
                         d_best_solo=st.mean(d_best),
                         d_best_solo_ci=list(np.percentile(d_best, [2.5, 97.5])))),
          open(f"{WS}/ai_native_academia/confounds.json", "w"), indent=1, default=float)
print("\nwrote confounds.json")

#!/usr/bin/env python3
"""APEX-REALISM step 4: landing model from the 81 live attempts.
Structural rule: our buy lands position A (first-or-revert passes) iff no OTHER non-bundle buy of >= THR SOL landed before
our tx (chain order).  Our arrival = clock offset from the create (slot units, idx/blocksize), measured on every attempt
(landed AND reverted txs both have a chain position).  P(A | launch) = P(our clk < clk of first relevant rival) using the
empirical distribution of our clk (leave-one-out for calibration)."""
import json, numpy as np, collections
X = json.load(open("/home/it/sniper-data/apex2/realism/live_tape.json"))
for THR in (0.0, 0.02, 0.05, 0.09):
    ok = 0; bad = []
    for x in X:
        rel = [a for a in x["ahead"] if a["k"] == "t" and a["sol"] >= THR and a["sol"] > 0]
        pred = not rel; act = x["outcome"] == "landed"
        ok += pred == act
        if pred != act: bad.append(f'{x["run"]}.{x["id"]}:{x["outcome"][:4]}')
    print(f"THR {THR}: rule matches {ok}/{len(X)}; misses {bad}")
THR = 0.05
oc = np.array([x["ours_tape"]["clk"] for x in X]); land = np.array([x["outcome"] == "landed" for x in X])
cls = np.array([x["cls"] for x in X]); u = np.array([x["ci"] / x["bsz"] for x in X])
def rclk(x):
    r = [o for o in x["others"] if o["sol"] >= THR]
    return r[0]["clk"] if r else 9.0
rc = np.array([rclk(x) for x in X])
print("\nour clk quantiles (slots after create):", np.round(np.quantile(oc, [.1, .25, .5, .75, .9]), 3), "mean", oc.mean().round(3))
for c in sorted(set(cls)):
    m = cls == c; print(f"  {c:9s} n={m.sum():2d} land {land[m].mean():.2f}  our clk median {np.median(oc[m]):.3f} q25 {np.quantile(oc[m], .25):.3f} q75 {np.quantile(oc[m], .75):.3f}")
for lo, hi in ((0, .25), (.25, .5), (.5, .75), (.75, 1.01)):
    m = (u >= lo) & (u < hi); print(f"  create u {lo}-{hi}: n={m.sum()} our clk median {np.median(oc[m]) if m.any() else 0:.3f} land {land[m].mean() if m.any() else 0:.2f}")
print("corr(our clk, u)", np.corrcoef(oc, u)[0, 1].round(3), " corr(our clk, log rival clk)", np.corrcoef(oc, np.log(rc))[0, 1].round(3))
# LOO calibration
p = np.array([np.mean(np.delete(oc, k) < rc[k]) for k in range(len(X))])
print(f"\nLOO predicted landings {p.sum():.1f} vs actual {land.sum()} of {len(X)}; Brier {np.mean((p - land) ** 2):.3f} (base {np.mean((land.mean() - land) ** 2):.3f})")
for lo, hi in ((0, .05), (.05, .2), (.2, .5), (.5, 1.0), (1.0, 99)):
    m = (rc >= lo) & (rc < hi)
    if m.any(): print(f"  first rival (>= {THR} SOL) clk {lo}-{hi}: n={m.sum():2d} predicted {p[m].mean():.2f} actual {land[m].mean():.2f}")
# per class conditional
pc = np.array([np.mean(np.delete(oc, k)[np.delete(cls, k) == cls[k]] < rc[k]) for k in range(len(X))])
print(f"class-conditional LOO: predicted {pc.sum():.1f}; Brier {np.mean((pc - land) ** 2):.3f}")
json.dump(dict(THR=THR, our_clk=oc.tolist(), cls=cls.tolist(), land=land.tolist(), rival_clk=rc.tolist(), u=u.tolist()),
          open("/home/it/sniper-data/apex2/realism/landing_model.json", "w"))

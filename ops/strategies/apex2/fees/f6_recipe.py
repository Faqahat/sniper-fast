#!/usr/bin/env python3
"""APEX-FEES step 6: what pay P (priority + tip, mSOL, per landed buy) maximises S2 at position A, per leader client,
with a FIRST-OR-REVERT guard (our buy reverts unless the curve is still at the post-bundle state -> only the base fee is lost).
Per UNSEEN S2 pick (walk-forward CREP at A, 0.4 SOL, exit h2):
  P(first | we land in the create slot) = prod_j q(P / pay_j) over the real non-bundle create-slot buyers j, where q(r) is the
  measured same-slot pairwise probability that the higher payer lands earlier (f4 section 3, per client; 1-q for r<1). [I]
  a = P(we land in the create slot at all) -- unobserved (our arrival); rows for a = 1.0 / 0.7 / 0.5.
  value if first = replay net at A (v) - P - sell cost ; else -base fee (5k, +prio if any; we assume tip-only => 5k).
Also: tiered P by creator's past competitor pay (walk-forward: median of the max rival pay on that creator's earlier judged launches)."""
import sys, json, collections, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2"); sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2/fees")
import a2_eval as E, fl

CL = ["AgaveBam", "JitoLabs", "HarmonicAgave", "HarmonicFiredancer", "Firedancer", "FireBAM"]
C, LT = fl.load()
tot = C["prio"] + C["tips"]
G = collections.defaultdict(list)
for k in np.flatnonzero((C["role"] == "buy") & (C["so"] == 0) & (C["rank"] >= 0)): G[C["mint"][k]].append(k)
for v in G.values(): v.sort(key=lambda k: C["i"][k])
LC = {l["mint"]: l["client"] for l in LT}
# pairwise q per client, from the data (tot metric), bins on ratio
RB = [1.0, 1.25, 1.5, 2, 3, 5, 10, 30, 1e12]
def qtable(cl):
    cnt = np.zeros((len(RB) - 1, 2))
    for m, v in G.items():
        if len(v) < 2 or (cl != "*" and C["client"][v[0]] != cl): continue
        for x in range(len(v)):
            for y in range(x + 1, len(v)):
                pa, pb = tot[v[x]], tot[v[y]]
                hi, lo = max(pa, pb), min(pa, pb)
                if hi == lo: continue
                r = hi / max(lo, 1e4); bi = min(np.searchsorted(RB, r, side="right") - 1, len(RB) - 2)
                cnt[bi, 0] += 1; cnt[bi, 1] += pa > pb
    return np.where(cnt[:, 0] > 30, cnt[:, 1] / np.maximum(cnt[:, 0], 1), np.nan)
Q = {cl: qtable(cl) for cl in CL + ["*"]}
for cl in Q:
    q = Q[cl]; qa = Q["*"]; Q[cl] = np.where(np.isnan(q), qa, q)
    Q[cl] = np.maximum.accumulate(Q[cl])          # monotone in ratio
print("pairwise q (P higher payer earlier) by ratio bin", RB[:-1])
for cl in Q: print(" ", cl, np.round(Q[cl], 2))
def q(cl, ours, theirs):
    if ours == theirs: return 0.5
    hi, lo = max(ours, theirs), min(ours, theirs); r = hi / max(lo, 1e4)
    bi = min(np.searchsorted(RB, r, side="right") - 1, len(RB) - 2); p = Q.get(cl, Q["*"])[bi]
    return p if ours > theirs else 1 - p

L = E.load(); bt = np.array([r[2] for r in L]); cb, cs_, _, _ = E.costs(L)
sel = E.crep(L, "same")["A"]; U = sel & (bt >= E.UNSEEN)
hrs = sum((min(b, bt.max()) - max(a, bt.min())) / 3600 for nm, a, b in E.WIN if a >= E.UNSEEN and ((bt >= a) & (bt < b)).any()); per = 24 / hrs
pi = E.POS.index("A"); zi = 2; xi = E.EXITS.index("h2")
picks = []
for i in np.flatnonzero(U):
    m = L[i][0]; v = [float(L[i][6][pi, zi, h, xi]) for h in range(3)]
    oth = [int(tot[k]) for k in G.get(m, [])]
    picks.append((m, LC.get(m, "?"), v, oth, L[i][1], L[i][2]))
print(f"unseen picks {len(picks)} ({len(picks)*per:.0f}/day); with a client {sum(p[1] != '?' for p in picks)}; contested (>=1 non-bundle cs buyer) {sum(len(p[3])>0 for p in picks)}")
BASE = 5000
PG = [0, 0.5, 1, 2, 3, 5, 8, 12, 16, 20, 25, 30, 40, 50, 75, 100]
def ev(sub, Pfun, a):
    out = np.zeros(3); nf = 0.0; cost = 0.0
    for p in sub:
        P = Pfun(p) * 1e6
        pf = a * np.prod([q(p[1], P, t) for t in p[3]]) if p[3] else a
        nf += pf
        for h in range(3):
            v = p[2][h]
            win = (v - P / 1e9 - cs_) if np.isfinite(v) else -BASE / 1e9
            out[h] += pf * win + (1 - pf) * (-BASE / 1e9)
        cost += pf * P / 1e9
    return out * per, nf * per, (cost / max(nf, 1e-9)) * 1e3
print("\n## Fixed P per client, a = P(land in create slot) [I]: SOL/day (phi 0 / -20% / -40% followers) | first fills/day | P(first) per pick")
best = {}
for a in (1.0, 0.7, 0.5):
    print(f"-- a = {a}")
    for cl in CL + ["*"]:
        sub = [p for p in picks if cl == "*" or p[1] == cl]
        if not sub: continue
        rows = []
        for P in PG:
            s, nf, _ = ev(sub, lambda p: P, a); rows.append((P, s, nf))
        b = max(rows, key=lambda r: r[1][0]); best[(cl, a)] = b[0]
        line = " ; ".join(f"P{r[0]:g}: {r[1][0]:+.2f}/{r[1][1]:+.2f}/{r[1][2]:+.2f} ({r[2]/len(sub)/per:.0%})" for r in rows if r[0] in (0, 1, 3, 5, 8, 16, 30, 50, 100))
        print(f"{cl} picks/day {len(sub)*per:.0f} | best P {b[0]:g} mSOL -> {b[1][0]:+.2f} SOL/d | {line}")
# per-client best P combined
print("\n## Combined: per-client best P (a = 1.0 fit) applied, by a [I]")
for a in (1.0, 0.7, 0.5):
    s, nf, c = ev(picks, lambda p: best.get((p[1], 1.0), best[("*", 1.0)]), a)
    print(f"a {a}: SOL/day {s[0]:+.2f} / f20 {s[1]:+.2f} / f40 {s[2]:+.2f}; first fills/day {nf:.0f}; mean pay per landed buy {c:.1f} mSOL")
# creator tier: walk-forward median of max rival pay on creator's earlier launches (create time < now - 300 s)
hist = collections.defaultdict(list); allp = []
for i in np.argsort(bt):
    m = L[i][0]; oth = [int(tot[k]) for k in G.get(m, [])]
    allp.append((bt[i], L[i][1], max(oth) if oth else 0, m))
allp.sort(); hz = collections.defaultdict(list); tierP = {}; j = 0
for t, cre, mx, m in allp:
    while j < len(allp) and allp[j][0] <= t - 300:
        hz[allp[j][1]].append(allp[j][2]); j += 1
    h = hz.get(cre, [])
    tierP[m] = np.median(h[-20:]) / 1e6 if h else None
print("\n## Creator-tier P = k x median(max rival pay on the creator's last 20 earlier launches), capped [I]")
for k_ in (0.5, 1.0, 1.5, 2.0):
    for cap in (16, 30, 60):
        f = lambda p: min(cap, max(1.0, k_ * tierP[p[0]])) if tierP.get(p[0]) is not None else 3.0
        for a in (1.0, 0.7):
            s, nf, c = ev(picks, f, a)
            print(f"k {k_} cap {cap} a {a}: SOL/day {s[0]:+.2f} / f20 {s[1]:+.2f} / f40 {s[2]:+.2f}; first/day {nf:.0f}; mean pay/landed {c:.1f} mSOL")
json.dump({"Q": {k: list(map(float, v)) for k, v in Q.items()}, "best_a1": {f"{k[0]}|{k[1]}": v for k, v in best.items()}},
          open("/home/it/sniper-data/apex2/fees/recipe.json", "w"))

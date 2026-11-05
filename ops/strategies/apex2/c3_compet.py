#!/usr/bin/env python3
"""APEX2 step 5: who sits in the create slot of S2 picks (walk-forward CREP at position A), where, what they pay, P&L."""
import sys, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/apex2")
import a2_eval as E
L = E.load(strings=True); bt = np.array([r[2] for r in L])
sel = E.crep(L, "same")["A"]; U = sel & (bt >= E.UNSEEN)
idx = np.flatnonzero(U)
hrs = sum((min(b, bt.max()) - max(a, bt.min())) / 3600 for nm, a, b in E.WIN if a >= E.UNSEEN and ((bt >= a) & (bt < b)).any())
per = 24 / hrs   # data hours only (the 11-01 recording gap is excluded)
print(f"S2(A) unseen picks {len(idx)} over {hrs:.1f} h ({len(idx)*per:.0f}/day); creators {len(set(L[i][1] for i in idx))}")
ncs = np.array([L[i][5]["ncs"] for i in idx]); nb = np.array([L[i][5]["nb"] for i in idx])
print("picks with >=1 non-bundle create-slot trade:", np.mean(ncs > 0).round(3), " bundle txs p50/p90:", np.percentile(nb, [50, 90]))
R = np.array([L[i][6][1, 2, 0, 0] for i in idx])
for nm, m in (("no create-slot snipers", ncs == 0), ("with snipers", ncs > 0)):
    v = R[m]; ok = np.isfinite(v)
    print(f"  {nm}: n {m.sum()}  A 0.4 curve net sum/day {np.nansum(v)*per:+.2f}  mean {np.nanmean(v)*1e3:+.2f} mSOL")
# per competitor wallet (event user) over picks
W = collections.defaultdict(lambda: dict(n=0, r0=0, ranks=[], offs=[], cost=[], pnl=0.0, fees=0.0, sol=0.0, launches=set(), cre=set(), held=[]))
firstoff = []; gap_after_bundle = []
for i in idx:
    info = L[i][5]; cst = info["cst"]; pn = info.get("cs_pnl", {})
    nb_ = info["nb"]
    nonb = [x for x in cst if not x[8] and x[4]]
    if nonb:
        firstoff.append(nonb[0][2])
        lastb = max([x[2] for x in cst if x[8]], default=0); gap_after_bundle.append(nonb[0][2] - lastb)
    seen = set()
    for rnk, x in enumerate(nonb):
        u = x[0]
        if u in seen: continue
        seen.add(u); w = W[u]; w["n"] += 1; w["r0"] += (rnk == 0); w["ranks"].append(rnk); w["offs"].append(x[2]); w["cost"].append(x[6] + x[7])
        w["sol"] += x[5] / 1e9; w["cre"].add(L[i][1])
        if u in pn:
            s, f, mk, b0, s0, nt = pn[u]; w["pnl"] += s + mk - f; w["fees"] += f
            if b0 is not None and s0 is not None: w["held"].append(s0 - b0)
print("first non-bundle buyer offset from create idx p10/50/90:", np.percentile(firstoff, [10, 50, 90]), " gap after bundle p10/50/90:", np.percentile(gap_after_bundle, [10, 50, 90]))
ws = sorted(W.items(), key=lambda kv: -kv[1]["n"])
print(f"distinct non-bundle create-slot buyers {len(ws)}")
print("wallet(user) | launches | %first | rank p50 | idx offset p50 | buy SOL avg | cost mSOL p50 | creators | P&L SOL/day | hold slots p50")
for u, w in ws[:25]:
    print(f"{u} | {w['n']} | {w['r0']/w['n']*100:.0f}% | {np.median(w['ranks']):.0f} | {np.median(w['offs']):.0f} | {w['sol']/w['n']:.3f} | {np.median(w['cost'])*1e-6:.2f} | {len(w['cre'])} | {w['pnl']*per:+.2f} | {np.median(w['held']) if w['held'] else float('nan'):.0f}")
# who is FIRST (rank 0) most often
r0 = sorted(W.items(), key=lambda kv: -kv[1]["r0"])
print("most often first after the bundle:")
for u, w in r0[:10]:
    print(f"  {u} first {w['r0']} of {w['n']} picks; P&L {w['pnl']*per:+.2f} SOL/day; cost p50 {np.median(w['cost'])*1e-6:.2f} mSOL")
c0 = [w["cost"][k] for u, w in W.items() for k in range(len(w["ranks"])) if w["ranks"][k] == 0]
print("cost of the FIRST non-bundle buyer (mSOL) p25/50/75/90:", np.percentile(c0, [25, 50, 75, 90]) * 1e-6)
tot = sum(w["pnl"] for w in W.values()); print(f"all non-bundle create-slot buyers on picks, total P&L {tot*per:+.2f} SOL/day")
# P&L by rank among non-bundle create-slot buyers
RK = collections.defaultdict(lambda: [0, 0.0, []])
for i in idx:
    info = L[i][5]; pn = info.get("cs_pnl", {}); seen = set()
    for rnk, x in enumerate([x for x in info["cst"] if not x[8] and x[4]]):
        if x[0] in seen or x[0] not in pn: continue
        seen.add(x[0]); s, f, mk, b0, s0, nt = pn[x[0]]; k = min(rnk, 5); RK[k][0] += 1; RK[k][1] += s + mk - f; RK[k][2].append(x[6] + x[7])
for k in sorted(RK): print(f"rank {k}{'+' if k == 5 else ''}: n {RK[k][0]}  P&L {RK[k][1]*per:+.2f} SOL/day  mean {RK[k][1]/RK[k][0]*1e3:+.1f} mSOL  cost p50 {np.median(RK[k][2])*1e-6:.2f} mSOL")
# bundle wallets (dev side) P&L
bp = 0.0
for i in idx:
    info = L[i][5]; pn = info.get("cs_pnl", {})
    for u in set(x[0] for x in info["cst"] if x[8]):
        if u in pn: s, f, mk, b0, s0, nt = pn[u]; bp += s + mk - f
print(f"creator-bundle wallets on picks: P&L {bp*per:+.2f} SOL/day")
pickle.dump({u: {k: (list(v) if isinstance(v, set) else v) for k, v in w.items()} for u, w in W.items()}, open("/home/moiz/sniper-data/apex2/compet.pkl", "wb"))

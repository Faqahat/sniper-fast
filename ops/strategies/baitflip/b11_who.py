#!/usr/bin/env python3
# WHO does the bait on chain? For every wallet: trips (per token) whose FIRST buy matches a bait rule
#   young: token 30-120 slots old, quiet >= 10 slots before the buy, curve (pre) <= 45 SOL, buy 0.9-2 SOL
#   quiet: token >= 150 slots old, quiet >= 40 slots, curve <= 40 SOL, buy 0.75-3 SOL
# realized trip P&L = SOL from its sells - SOL into its buys (pump fee included in event amounts? -> we add 1.25%/side)
# - tx fees + tips; unsold tokens at end valued at curve liquidation (status O). Also follower-within-1-slot rate.
import gzip, json, collections, statistics as st, sys
from multiprocessing import Pool
import b1_scan as B
B.RUNS = {**B.RUNS, "R4": ["phaseA_r4"]}
def job(a):
    run, b = a; out = []
    for m, tr in B.read(run, b).items():
        if len(tr) < 5 or any(t[11] < 25e9 or t[11] > 200e9 or not t[12] for t in tr[:50]): continue
        s0 = tr[0][0]; firstbuy = {}
        for k, t in enumerate(tr):
            if not t[8] or t[7] in firstbuy: 
                if t[8]: continue
                continue
            firstbuy[t[7]] = k
        for u, k in firstbuy.items():
            if k == 0: continue
            t = tr[k]; age = t[0] - s0; quiet = t[0] - tr[k - 1][0]; pv = B.pre(t)[0]; sol = t[9]
            kind = None
            if 30 <= age <= 120 and quiet >= 10 and pv <= 45e9 and 0.9e9 <= sol <= 2e9: kind = "young"
            elif age >= 150 and quiet >= 40 and pv <= 40e9 and 0.75e9 <= sol <= 3e9: kind = "quiet"
            if not kind or t[11] >= B.GRADV: continue
            spent = got = cost = 0; tok = 0; sigs = set(); last = None; grad = False
            for z in tr[k:]:
                if z[11] >= B.GRADV: grad = True
                if z[7] != u: continue
                if z[3] not in sigs: sigs.add(z[3]); cost += z[5] + z[6]
                if z[8]: spent += z[9] * 1.0125; tok += z[10]
                else: got += z[9] * 0.9875; tok -= z[10]
                last = z
            if grad: continue
            fv, ft = tr[-1][11], tr[-1][12]
            rem = max(0, tok); got += fv * rem / (ft + rem) * 0.9875 if rem > 1e6 else 0
            fol = any(z[7] != u and z[8] and z[0] <= t[0] + 1 for z in tr[k + 1:k + 40])
            out.append((run, u, kind, m, t[0], round(sol / 1e9, 3), round((got - spent - cost) / 1e9, 5), fol, (last[0] - t[0]) if last else 0, t[3]))
    return out
if __name__ == "__main__":
    E = []
    with Pool(12) as p:
        for e in p.imap_unordered(job, [(r, b) for r in B.RUNS for b in range(256)]): E += e
    json.dump(E, open("/home/moiz/sniper-data/strategies/baitflip/who_trips.json", "w"))
    W = collections.defaultdict(list)
    for e in E: W[e[1]].append(e)
    rows = []
    for u, es in W.items():
        if len(es) < 15: continue
        byrun = collections.defaultdict(float)
        for e in es: byrun[e[0]] += e[6]
        pos_days = sum(1 for r in byrun.values() if r > 0)
        rows.append((sum(e[6] for e in es), u, len(es), byrun, pos_days, es))
    rows.sort(reverse=True)
    print("wallet | baits | total P&L | per run | days positive | win | follower<=1 slot | kinds | median size | median hold slots")
    for tot, u, n, byrun, pd, es in rows[:25]:
        k = collections.Counter(e[2] for e in es)
        print(f"{u} {n:4d} {tot:+7.2f} {dict((r, round(v,2)) for r, v in sorted(byrun.items()))} {pd}/{len(byrun)} "
              f"win {100*sum(e[6]>0 for e in es)/n:.0f}% fol {100*sum(e[7] for e in es)/n:.0f}% {dict(k)} {st.median(e[5] for e in es):.2f} {st.median(e[8] for e in es):.0f}")

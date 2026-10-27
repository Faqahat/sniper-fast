#!/usr/bin/env python3
# Top PumpSwap winners (both days positive): how they trade, and can we copy them? Copy = our 1 SOL buy lands T ms after their FIRST buy
# in a pool (T = 200, 500, 1000, 3000), exit = T ms after their first sell (mirror) or timers (1 / 5 / 15 min). Constant-product replay.
import pickle, collections, json, statistics
from multiprocessing import Pool
S = pickle.load(open("study.pkl", "rb")); WA = S["W"]
top = []
for u, d in WA.items():
    if "R2" in d and "R3" in d and d["R2"][0] >= 20 and d["R3"][0] >= 20 and d["R2"][1] > 0 and d["R3"][1] > 0:
        top.append((d["R2"][1] / 21.8 * 24 + d["R3"][1], u))
top = [u for _, u in sorted(top, reverse=True)[:40]]; TOP = set(top)
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(s, i): return s * 212.0 + i / max(SS.get(s, 0), i + 1, 380) * 212.0
FEE = 0.0095; TX = 0.0015; B = 1.0
def clean(v):
    """drop dust / mis-parsed rows: keep q >= 0.01 SOL and an implied pool SOL reserve within 10% of the running reserve"""
    out = []; Q = None
    for r in v:
        if r[7] < 10_000_000 or r[9] <= 0 or r[10] <= 0: continue
        if Q is None:
            near = sorted(x[10] for x in v[:12] if x[7] >= 10_000_000 and x[10] > 0)
            Q = near[len(near) // 2] if near else r[10]
        if abs(r[10] / Q - 1) > 0.10: continue
        out.append(r); Q = r[10] + r[7] if r[5] else r[10] - r[7]
    return out
def load(b):
    rows = []
    with open(f"bk/{b:02d}.pkl", "rb") as f:
        while True:
            try: rows += pickle.load(f)
            except EOFError: break
    by = collections.defaultdict(list)
    for r in rows: by[r[0]].append(r)
    for m in list(by):
        by[m].sort(key=lambda r: (r[1], r[2])); by[m] = clean(by[m])
    return by
def path_after(v, k, T):
    t0 = ms(v[k][1], v[k][2]); j = k
    while j + 1 < len(v) and ms(v[j + 1][1], v[j + 1][2]) - t0 <= T: j += 1
    r = v[j]; Bq = r[9] - r[6] if r[5] else r[9] + r[6]; Qq = r[10] + r[7] if r[5] else r[10] - r[7]
    if Bq <= 0 or Qq <= 0: return None, None
    X = B * 1e9 * (1 - FEE); tok = Bq * X / (Qq + X); Bq -= tok; Qq += X
    fill = t0 + T; path = [(fill, Qq * tok / (Bq + tok) * (1 - FEE) / 1e9)]
    for x in v[j + 1:]:
        mt = ms(x[1], x[2])
        if mt - fill > 1_000_000: break
        if x[5]: dq = x[7]; Bq, Qq = Bq * Qq / (Qq + dq), Qq + dq
        else: db = x[6]; Bq, Qq = Bq + db, Qq * Bq / (Bq + db)
        path.append((mt, Qq * tok / (Bq + tok) * (1 - FEE) / 1e9))
    return path, ((Qq / Bq) / (v[k][10] / v[k][9])) if v[k][10] > 0 and v[k][9] > 0 else 1.0
def work(b):
    by = load(b); out = []
    for m, v in by.items():
        if len(v) < 2: continue
        users = {r[4] for r in v} & TOP
        for u in users:
            ks = [k for k, r in enumerate(v) if r[4] == u]
            k0 = next((k for k in ks if v[k][5]), None)
            if k0 is None: continue
            sells = [k for k in ks if not v[k][5] and k > k0]
            bq = sum(v[k][7] for k in ks if v[k][5]); sq = sum(v[k][7] for k in sells)
            bb = sum(v[k][6] for k in ks if v[k][5]); sb = sum(v[k][6] for k in sells)
            t_first = ms(v[0][1], v[0][2]); t0 = ms(v[k0][1], v[k0][2])
            pre = [r for r in v[:k0] if t0 - ms(r[1], r[2]) <= 60_000]
            p60 = ((v[k0][10] / v[k0][9]) / (pre[0][10] / pre[0][9]) - 1) if (pre and pre[0][10] > 0 and v[k0][9] > 0 and pre[0][9] > 0) else 0
            bigsell = any((not r[5]) and r[7] >= 3e9 for r in v[max(0, k0 - 3):k0])
            o = dict(u=u, m=m, run=v[k0][11], size=bq / 1e9, nb=sum(1 for k in ks if v[k][5]), ns=len(sells), closed=sb >= 0.98 * bb,
                     pnl=(sq * (1 - FEE) - bq * (1 + FEE)) / 1e9, hold=(ms(v[sells[-1]][1], v[sells[-1]][2]) - t0) / 1000 if sells else None,
                     first_sell=(ms(v[sells[0]][1], v[sells[0]][2]) - t0) / 1000 if sells else None, pool_age=(t0 - t_first) / 1000,
                     reserve=v[k0][10] / 1e9, ch60=p60, bigsell=bigsell, copy={})
            for T in (200, 500, 1000, 3000):
                path, over = path_after(v, k0, T)
                if not path: continue
                at = lambda sec, path=path: [p for m_, p in path if m_ - path[0][0] <= sec * 1000][-1]
                c = {f"t{s}": at(s) - B - 2 * TX for s in (60, 300, 900)}
                if sells:
                    ts = ms(v[sells[0]][1], v[sells[0]][2]) + T
                    c["mirror"] = [p for m_, p in path if m_ <= ts][-1] - B - 2 * TX
                c["over"] = over - 1
                o["copy"][T] = c
            out.append(o)
    return out
if __name__ == "__main__":
    P = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, range(64)): P += o
    pickle.dump(P, open("winners.pkl", "wb"))
    med = lambda v: statistics.median(v) if v else float("nan")
    print("per wallet (both days): positions | realized | win | size | hold median (s) | first sell (s) | pool age at entry (min) | pool SOL | price chg 60s before | after a >=3 SOL sell")
    for u in top[:25]:
        v = [o for o in P if o["u"] == u and o["closed"]]
        if not v: continue
        print(f"  {u[:8]} {len(v):4d} | {sum(o['pnl'] for o in v):+7.1f} | {sum(o['pnl'] > 0 for o in v)/len(v):4.0%} | {med([o['size'] for o in v]):6.2f} | {med([o['hold'] for o in v]):7.0f} | {med([o['first_sell'] for o in v]):6.0f} | "
              f"{med([o['pool_age'] for o in v]) / 60:7.0f} | {med([o['reserve'] for o in v]):5.0f} | {med([o['ch60'] for o in v]):+6.1%} | {sum(o['bigsell'] for o in v)/len(v):4.0%}")
    print("\nCOPY their first buy in a pool, 1 SOL (all top-40 wallets pooled; R2 / R3 totals):")
    for T in (200, 500, 1000, 3000):
        for k in ("mirror", "t60", "t300", "t900"):
            for run in ("R2", "R3"):
                x = [o["copy"][T][k] for o in P if o["run"] == run and T in o["copy"] and k in o["copy"][T]]
                if x: print(f"  T={T:4d} ms exit {k:6s} {run} n={len(x):5d} total {sum(x):+7.1f} per copy {sum(x)/len(x):+.4f} up {sum(1 for y in x if y > 0)/len(x):.0%}")
        print(f"  T={T:4d} ms: we pay median {med([o['copy'][T]['over'] for o in P if T in o['copy']]):+.2%} vs their fill")
    print("\nCOPY per wallet (T=1000 ms, mirror exit), R2 / R3:")
    for u in top[:25]:
        r2 = [o["copy"][1000]["mirror"] for o in P if o["u"] == u and o["run"] == "R2" and 1000 in o["copy"] and "mirror" in o["copy"][1000]]
        r3 = [o["copy"][1000]["mirror"] for o in P if o["u"] == u and o["run"] == "R3" and 1000 in o["copy"] and "mirror" in o["copy"][1000]]
        print(f"  {u}  R2 {sum(r2):+6.2f} ({len(r2)}) | R3 {sum(r3):+6.2f} ({len(r3)})")

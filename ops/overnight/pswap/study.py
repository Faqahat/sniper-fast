#!/usr/bin/env python3
# PumpSwap study (read-only): (A) wallet census per run (realized PnL on closed positions, 0.95% fee/side), (B) generic trigger replays at our
# speed: dip (a sell >= X SOL), momentum (others net-bought >= Y SOL in 10 s), graduation (first PumpSwap trades of a fresh pool).
# Our 1 SOL buy lands T ms (block position) after the trigger; constant-product replay with our impact; exits are timers.
import pickle, glob, collections, json, statistics
from multiprocessing import Pool
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(s, i): return s * 212.0 + i / max(SS.get(s, 0), i + 1, 380) * 212.0
FEE = 0.0095; TX = 0.0015; B = 1.0; HOLDS = (1, 3, 10, 30, 60, 300)
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
def replay(v, k, T):
    """our buy after trigger row k, landing T ms later; returns pnl per hold"""
    t0 = ms(v[k][1], v[k][2]); j = k
    while j + 1 < len(v) and ms(v[j + 1][1], v[j + 1][2]) - t0 <= T: j += 1
    r = v[j]; Bq = r[9] - r[6] if r[5] else r[9] + r[6]; Qq = r[10] + r[7] if r[5] else r[10] - r[7]   # state AFTER row j
    if Bq <= 0 or Qq <= 0: return None
    X = B * 1e9 * (1 - FEE); tok = Bq * X / (Qq + X); Bq -= tok; Qq += X
    fill = t0 + T; res = {}; hi = 0
    val = lambda Bq, Qq: Qq * tok / (Bq + tok) * (1 - FEE) / 1e9
    path = [(fill, val(Bq, Qq))]
    for x in v[j + 1:]:
        mt = ms(x[1], x[2])
        if mt - fill > 310_000: break
        if x[5]: dq = x[7]; Bq2 = Bq * Qq / (Qq + dq); Bq, Qq = Bq2, Qq + dq
        else: db = x[6]; Qq2 = Qq * Bq / (Bq + db); Bq, Qq = Bq + db, Qq2
        path.append((mt, val(Bq, Qq)))
    for h in HOLDS: res[h] = [p for m_, p in path if m_ - fill <= h * 1000][-1] - B - 2 * TX
    return res
def work(b):
    by = load(b); W = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0, 0.0, []]))
    trig = collections.defaultdict(list)
    for m, v in by.items():
        if len(v) < 2: continue
        # census
        pos = collections.defaultdict(lambda: dict(bq=0, sq=0, bb=0, sb=0, t0=None, t1=None, run=None))
        for r in v:
            p = pos[r[4]]
            if r[5]: p["bq"] += r[7]; p["bb"] += r[6]; p["t0"] = p["t0"] or r[3]; p["run"] = p["run"] or r[11]
            else: p["sq"] += r[7]; p["sb"] += r[6]; p["t1"] = r[3]
        for u, p in pos.items():
            if not p["bb"] or p["sb"] < 0.98 * p["bb"]: continue
            pnl = (p["sq"] * (1 - FEE) - p["bq"] * (1 + FEE)) / 1e9 - 2 * TX
            w = W[u][p["run"]]; w[0] += 1; w[1] += pnl; w[2] += pnl > 0; w[3] += p["bq"] / 1e9; w[4].append((p["t1"] or p["t0"]) - p["t0"])
        # triggers
        first = v[0]
        if 75e9 <= first[10] <= 95e9:
            for T in (75, 1000):
                rr = replay(v, 0, T)
                if rr: trig[("grad", T, first[11])].append(rr)
        last_mom = -1e18
        for k, r in enumerate(v):
            if not r[5]:
                for X in (1, 3, 10):
                    if r[7] >= X * 1e9:
                        for T in (35, 75):
                            rr = replay(v, k, T)
                            if rr: trig[(f"dip{X}", T, r[11])].append(rr)
            else:
                t0 = ms(r[1], r[2])
                if t0 - last_mom > 60_000:
                    net = 0.0; j = k
                    while j >= 0 and t0 - ms(v[j][1], v[j][2]) <= 10_000:
                        net += v[j][7] if v[j][5] else -v[j][7]; j -= 1
                    for Y in (5, 20):
                        if net >= Y * 1e9:
                            last_mom = t0
                            rr = replay(v, k, 75)
                            if rr: trig[(f"mom{Y}", 75, r[11])].append(rr)
                            break
    return {u: {run: (w[0], w[1], w[2], w[3], statistics.median(w[4]) if w[4] else 0) for run, w in d.items()} for u, d in W.items()}, dict(trig)
if __name__ == "__main__":
    WA = {}; TR = collections.defaultdict(list)
    with Pool(8) as p:
        for w, t in p.imap_unordered(work, range(64)):
            for u, d in w.items():
                e = WA.setdefault(u, {})
                for run, x in d.items():
                    if run in e: a = e[run]; e[run] = (a[0] + x[0], a[1] + x[1], a[2] + x[2], a[3] + x[3], max(a[4], x[4]))
                    else: e[run] = x
            for k, v in t.items(): TR[k] += v
    pickle.dump(dict(W=WA, T=dict(TR)), open("study.pkl", "wb"))
    print("=== B. trigger replays (1 SOL; total SOL / share up) R2 = 21.8 h, R3 = 24 h")
    for key in sorted({(k[0], k[1]) for k in TR}):
        for run in ("R2", "R3"):
            v = TR.get((key[0], key[1], run), [])
            if not v: continue
            print(f"  {key[0]:6s} T={key[1]:4d} {run} n={len(v):6d} | " + " | ".join(f"{h}s {sum(x[h] for x in v):+8.1f} ({sum(1 for x in v if x[h] > 0) / len(v):.0%})" for h in HOLDS))
    print("\n=== A. consistent PumpSwap winners: closed positions >= 20 on BOTH days, both days > 0 (realized, 0.95% fee/side)")
    rows = []
    for u, d in WA.items():
        if "R2" in d and "R3" in d and d["R2"][0] >= 20 and d["R3"][0] >= 20 and d["R2"][1] > 0 and d["R3"][1] > 0:
            rows.append((d["R2"][1] / 21.8 * 24 + d["R3"][1], u, d))
    rows.sort(reverse=True)
    print(f"  wallets: {len(rows)}")
    for tot, u, d in rows[:30]:
        print(f"  {u}  R2 {d['R2'][1]:+7.1f} ({d['R2'][0]} pos, win {d['R2'][2]/d['R2'][0]:.0%}) | R3 {d['R3'][1]:+7.1f} ({d['R3'][0]} pos, win {d['R3'][2]/d['R3'][0]:.0%}) | avg size {d['R3'][3]/d['R3'][0]:.2f} SOL")

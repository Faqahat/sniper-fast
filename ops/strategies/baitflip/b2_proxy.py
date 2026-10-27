#!/usr/bin/env python3
# BAIT-FLIP pass 2 (proxy). On chain our bundle looks like: SELL X  ->  BUY ~X right behind it (price back to ~pre-sell).
# Real proxy: a sell >= 0.3 SOL whose very next trade (same slot) is a BUY by another wallet that puts the price back.
# For each anchor we measure, AFTER the anchor point, outside buys/sells and price vs the pre-sell price p0:
#   kind "rest"  = sell + same-slot restoring buy (rr = price after buy / p0)       -> the bait proxy
#   kind "dump"  = sell, next trade not a same-slot buy                              -> what dip bots normally get
#   kind "base"  = every 8th ordinary trade (no sell >= 0.3 in this slot so far)      -> holding without any bait
# Known dip bots (dip census) flagged separately.
import os, json, gzip, collections
from multiprocessing import Pool
import b1_scan as B
OUT = "/home/moiz/sniper-data/strategies/baitflip2"
PFX = ("haqqiUUX", "HkQ7hMjy", "DYXDDrZC", "E6JasdE8", "7PedQZm", "CZ77onJz", "6VzXcLk9", "ETwEAQPL", "sssssDdM", "ssssswdk", "9pQQc1xy")
WIN = [0, 1, 2, 3, 4, 6, 8, 12]

def out_after(tr, ka, slot, p0, excl):
    n = len(tr); res = {}
    for w in WIN:
        smax = slot + w; nb = ns = nd = 0; bs = ss = 0.0; ws = set(); plast = None; pmax = 0
        kk = ka + 1
        while kk < n and tr[kk][0] <= smax:
            t = tr[kk]
            if t[11] >= B.GRADV: break
            if t[7] not in excl:
                if t[8]:
                    nb += 1; bs += t[9]; ws.add(t[7])
                    if t[7].startswith(PFX): nd += 1
                else: ns += 1; ss += t[9]
            plast = B.px(t[11], t[12]); pmax = max(pmax, plast); kk += 1
        pa = B.px(tr[ka][11], tr[ka][12])
        plast = plast or pa; pmax = max(pmax, pa)
        res[w] = (nb, round(bs / 1e9, 3), len(ws), nd, ns, round(ss / 1e9, 3), round(plast / p0, 5), round(pmax / p0, 5))
    return res

def scan(job):
    run, b = job
    rows = []
    for m, tr in B.read(run, b).items():
        if len(tr) < 5: continue
        if any(t[11] < 25e9 or t[11] > 200e9 or not t[12] for t in tr[:50]): continue
        s0 = tr[0][0]; n = len(tr); bigsell_slot = -1; lo = 0
        for k, t in enumerate(tr):
            while tr[lo][0] < t[0] - 20: lo += 1
            pre20 = tr[lo:k]
            ctx = {"n20": len(pre20), "b20": round(sum(z[9] for z in pre20 if z[8]) / 1e9, 2), "s20": round(sum(z[9] for z in pre20 if not z[8]) / 1e9, 2),
                   "r20": round(B.px(t[11], t[12]) / B.px(*B.pre(tr[lo])), 3) if k > lo else 1.0}
            if t[11] >= B.GRADV: break
            age = t[0] - s0
            if not t[8] and t[9] >= 0.3e9:
                bigsell_slot = t[0]
                pv, pt = B.pre(t); p0 = B.px(pv, pt)
                nx = tr[k + 1] if k + 1 < n else None
                base = {"run": run, "m": m, "s": t[0], "age": age, "sell": round(t[9] / 1e9, 3), "vsol": round(pv / 1e9, 2),
                        "drop": round(B.px(t[11], t[12]) / p0 - 1, 4), "seller": t[7][:8], **ctx}
                if nx and nx[0] == t[0] and nx[8] and nx[7] != t[7]:
                    rr = B.px(nx[11], nx[12]) / p0
                    rows.append(dict(base, kind="rest", rr=round(rr, 4), rbuy=round(nx[9] / 1e9, 3), rdi=nx[1] - t[1],
                                     rdip=nx[7].startswith(PFX), out=out_after(tr, k + 1, t[0], p0, {t[7], nx[7]})))
                else:
                    rows.append(dict(base, kind="dump", out=out_after(tr, k, t[0], p0, {t[7]})))
            elif k % 4 == 0 and bigsell_slot != t[0] and age > 0:
                p0 = B.px(t[11], t[12])
                rows.append({"run": run, "m": m, "s": t[0], "age": age, "vsol": round(t[11] / 1e9, 2), "kind": "base",
                             "bside": t[8], "bsol": round(t[9] / 1e9, 3), **ctx, "out": out_after(tr, k, t[0], p0, {t[7]})})
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(f"{OUT}/{run}_b{b:03d}.jsonl.gz", "wt") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    c = collections.Counter(r["kind"] for r in rows)
    return run, b, c

if __name__ == "__main__":
    jobs = [(r, b) for r in B.RUNS for b in range(256)]
    tot = collections.Counter()
    with Pool(12) as p:
        for i, (run, b, c) in enumerate(p.imap_unordered(scan, jobs)):
            for k, v in c.items(): tot[run + "_" + k] += v
            if i % 64 == 0: print(i, dict(tot), flush=True)
    print("DONE", dict(tot), flush=True)

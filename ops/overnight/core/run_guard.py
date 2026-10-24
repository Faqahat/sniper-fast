#!/usr/bin/env python3
# PRICE GUARD (read-only): our buy carries a min-out so it FAILS if the price at our fill is more than G above the
# post-bundle price (= other buyers got in first). A failed buy costs only the failed-tx fee (tips revert / the nonce copy
# never lands). Selections: S3 list, union list, all launches. Exit: sell landing 500 ms after the create (timed).
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
exec(open("/home/moiz/sniper/ops/overnight/core/ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
MS = [r["mint"] for r in rows]
byb = collections.defaultdict(set)
for m in MS: byb[rp.bucket(m)].add(m)
GUARDS = (None, 0.01, 0.03, 0.06, 0.10, 0.20)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        ge = tr[st["g_end"] - 1] if st["g_end"] > 0 else None
        if ge is None: continue
        p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, bt=c["bt"], s3=m in S3, res={})
        for Lm in (35, 45, 60, 75):
            ib, _ = rp.place(tr, c, st, O[m]["outs"], Lm)
            if ib < 1: continue
            pf = tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]
            pnl = rp.flip(tr, ib, rp.place_ms(tr, c, st, O[m]["outs"], 500, ib), 0.5)
            r["res"][Lm] = (pf / p_b, pnl)
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    for selname, sel in (("S3 list", lambda r: r["s3"]), ("ALL launches", lambda r: True)):
        R = [r for r in res if sel(r)]
        print(f"\n== {selname}: {len(R)} launches; sell lands 500 ms after the create; failed buy costs FAIL SOL")
        for FAIL in (0.0005, 0.002):
            for G in GUARDS:
                cells = []
                for Lm in (35, 45, 60, 75):
                    tot = 0.0; n_fill = 0; a = 0.0
                    for r in R:
                        if Lm not in r["res"]: continue
                        ratio, pnl = r["res"][Lm]
                        v = pnl if (G is None or ratio <= 1 + G) else -FAIL
                        n_fill += (G is None or ratio <= 1 + G); tot += v; a += v if r["bt"] < mid else 0
                    cells.append(f"L{Lm} {tot:+7.2f} ({a:+.1f}/{tot - a:+.1f}) fills {n_fill}")
                print(f"   guard {'none' if G is None else f'{G:.0%}':>4} fail {FAIL}: " + " | ".join(cells))
            if selname == "ALL launches": break

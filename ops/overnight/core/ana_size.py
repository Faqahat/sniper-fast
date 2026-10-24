# S3 forward window: size scaling at L35/L45/L60 with the timed sell (500 ms), costs as % overhead vs a fixed per-buy fee
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
exec(open("ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
res = collections.defaultdict(list)
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        for Lm in (35, 45, 60):
            ib, _ = rp.place(tr, c, st, O[m]["outs"], Lm)
            if ib < 1: continue
            isell = rp.place_ms(tr, c, st, O[m]["outs"], 500, ib)
            for B in (0.25, 0.5, 1.0, 2.0, 3.0):
                res[(Lm, B, "2%")].append(rp.flip(tr, ib, isell, B, fee_buy_pct=0.02))
                res[(Lm, B, "fix0.005")].append(rp.flip(tr, ib, isell, B, fee_buy_pct=0.0) - 0.005)
for Lm in (35, 45, 60):
    print(f"L{Lm}: " + " | ".join(f"B{B}: {sum(res[(Lm, B, '2%')]):+6.2f} (fixed-fee {sum(res[(Lm, B, 'fix0.005')]):+6.2f})" for B in (0.25, 0.5, 1.0, 2.0, 3.0)))

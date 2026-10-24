# calibration on the forward window: S3 launches, eos1 PnL with the REAL arrival-time placement vs the block-position PROXY
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
exec(open("ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs(); EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
res = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        for Lm in (35, 60, 75):
            i1, n1 = rp.place(tr, c, st, O[m]["outs"], Lm); i2, n2 = rp.place_proxy(tr, c, st, Lm)
            a = rp.sim(tr, c, st, i1, 0.5, EX, fill_pen=0.015); b2 = rp.sim(tr, c, st, i2, 0.5, EX, fill_pen=0.015)
            if a and b2:
                x = res[Lm]; x[0] += a["eos1"]["pnl"]; x[1] += b2["eos1"]["pnl"]; x[2] += 1; x[3] += (i1 == i2)
for Lm, (a, b2, n, same) in sorted(res.items()):
    print(f"L{Lm}: n {n} real-placement eos1 {a:+.2f} SOL | proxy-placement {b2:+.2f} SOL | same entry index {same / n:.0%}")

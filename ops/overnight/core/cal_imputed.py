import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
exec(open("ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs(); EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
res = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0])
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        for Lm in (35, 45, 60, 75):
            i1, _ = rp.place(tr, c, st, O[m]["outs"], Lm); i2, _ = rp.place_imputed(tr, c, st, O[m]["outs"], Lm)
            a = rp.sim(tr, c, st, i1, 0.5, EX, fill_pen=0.015); b2 = rp.sim(tr, c, st, i2, 0.5, EX, fill_pen=0.015)
            s1 = rp.flip(tr, i1, rp.place_ms(tr, c, st, O[m]["outs"], 500, i1), 0.5); s2 = rp.flip(tr, i2, rp.place_ms(tr, c, st, O[m]["outs"], 500, i2), 0.5)
            if a and b2:
                x = res[Lm]; x[0] += a["eos1"]["pnl"]; x[1] += b2["eos1"]["pnl"]; x[2] += s1; x[3] += s2; x[4] += 1
for Lm, (a, b2, s1, s2, n) in sorted(res.items()):
    print(f"L{Lm}: n {n} | eos1: standard {a:+.2f} vs imputed-unseen {b2:+.2f} | sell@500ms: standard {s1:+.2f} vs imputed {s2:+.2f}")

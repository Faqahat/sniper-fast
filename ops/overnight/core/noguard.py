# S3 picks WITHOUT the price guard (same placement/exit as S4) -> report/noguard.json
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
FW = json.load(open("/home/moiz/sniper/ops/overnight/report/s4_forward.json"))
L = rp.load_launches(); O = rp.load_obs(); EX = [rp.R("hold1s", [(1.0, ("t", 1))], 2), rp.R("eos1", [(1.0, ("slot", 1))], 5)]
byb = collections.defaultdict(set)
for r in FW: byb[rp.bucket(r["mint"])].add(r["mint"])
tot = collections.defaultdict(float)
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms); fa = rp.read_failed("R2", b, ms)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015)
            if o:
                for k in o: tot[f"{k}_{Lm}"] += o[k]["pnl"]
json.dump(dict(tot), open("/home/moiz/sniper/ops/overnight/report/noguard.json", "w"))
print({k: round(v, 2) for k, v in sorted(tot.items())})

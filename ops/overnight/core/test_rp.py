import sys, time, json, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); O = rp.load_obs()
fw = [m for m in O if m in L and L[m]["run"] == "R2"]
print("launches with timeline in R2:", len(fw))
import random; random.seed(1); samp = random.sample(fw, 300)
byb = {}
for m in samp: byb.setdefault(rp.bucket(m), set()).add(m)
rules = rp.default_rules(); print("rules:", len(rules))
t0 = time.time(); n = 0; ntr = []; res = []
for b, ms in list(byb.items())[:40]:
    tr_all = rp.read_bucket("R2", b, ms)
    for m in ms:
        tr = tr_all.get(m)
        if not tr: continue
        c = L[m]; st = rp.structure(tr, c)
        idx, na = rp.place(tr, c, st, O[m]["outs"], 75)
        r = rp.sim(tr, c, st, idx, 0.5, rules)
        n += 1; ntr.append(len(tr))
        if r: res.append((m, na, len(tr), r["hold5s"]["pnl"], r["hold60s"]["pnl"], r["fsell_out"]["pnl"], r["lad_50@1.5_25@2_25@3_sl.7"]["pnl"]))
print(f"{n} launches simulated in {time.time() - t0:.1f}s; trades per launch median {statistics.median(ntr)} max {max(ntr)}")
for x in res[:12]: print(x)
print("mean pnl hold5s", statistics.mean(x[3] for x in res), "hold60s", statistics.mean(x[4] for x in res), "fsell_out", statistics.mean(x[5] for x in res))

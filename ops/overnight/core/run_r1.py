#!/usr/bin/env python3
# OLD-DATA REPLAY (R1: 10-21 22:07 -> 10-22 ~07:00 UTC, before the forward window; no arrival timelines exist there):
# S3 deployer list (walk-forward: only attempts/launches before each launch), our entry by the block-position landing
# proxy (calibrated on the forward window: equal at 35 ms, pessimistic at 60-75 ms), same exits and costs.
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); A = json.load(open("attempts.json")); DC = "/home/moiz/sniper/ops/snipers/devcheck"
ev = []
for w in ("9Sh2fd", "DGmspi"):
    for f in (f"devs_{w}.json", f"att_{w}.json"):
        p = os.path.join(DC, f)
        if os.path.exists(p):
            for m, v in json.load(open(p)).items():
                if v.get("signer") and v.get("bt") and m not in L: ev.append((v["bt"], v["signer"], "att"))
for m, c in L.items():
    if not c.get("bt"): continue
    ev.append((c["bt"], c["user"], "launch"))
    if "9Sh2fd" in A.get(m, {}) or "DGmspi" in A.get(m, {}): ev.append((c["bt"], c["user"], "att"))
ev.sort()
R1 = sorted([(c["bt"], m) for m, c in L.items() if c["run"] == "R1" and c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or [])])
natt = collections.Counter(); nl = collections.Counter(); k = 0; pick = {}
for bt, m in R1:
    while k < len(ev) and ev[k][0] < bt:
        t, d, kind = ev[k]; (natt if kind == "att" else nl)[d] += 1; k += 1
    d = L[m]["user"]; a, n = natt[d], nl[d]
    if a >= 2 and (n == 0 or a / n >= 0.10): pick[m] = (a, n)
R = rp.R
RULES = [R("eos0", [(1.0, ("slot", 0))], 5), R("eos1", [(1.0, ("slot", 1))], 5), R("eos2", [(1.0, ("slot", 2))], 5), R("hold1s", [(1.0, ("t", 1))], 2),
         R("hold5s", [(1.0, ("t", 5))], 6), R("hold10s", [(1.0, ("t", 10))], 11), R("hold30s", [(1.0, ("t", 30))], 31),
         R("tp1.1_eos2", [(1.0, ("x", 1.1)), (1.0, ("slot", 2))], 5),
         R("pD_25at_slots1_3_6_10", [(0.25, ("slot", 1)), (0.25, ("slot", 3)), (0.25, ("slot", 6)), (0.25, ("slot", 10))], 5),
         R("twap_10pct_every2s_20s", [(0.1, ("t", 2 * j)) for j in range(1, 11)], 21),
         R("lad_33@1.3_33@1.6_trail", [(0.33, ("x", 1.3)), (0.33, ("x", 1.6)), (1.0, ("dd", 1.6, 0.2)), (1.0, ("sl", 0.75))], 300),
         R("lad_50@1.5_25@2_25@3_sl.7", [(0.5, ("x", 1.5)), (0.25, ("x", 2.0)), (0.25, ("x", 3.0)), (1.0, ("sl", 0.7))], 300)]
NAMES = [r["name"] for r in RULES]
byb = collections.defaultdict(set)
for m in pick: byb[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R1", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); r = dict(m=m, bt=c["bt"], res={})
        for Lm in (0, 35, 45, 60, 75):
            idx, n = rp.place_proxy(tr, c, st, Lm) if Lm else (st["g_end"], 0)
            if idx < 1: continue
            o = rp.sim(tr, c, st, idx, 0.5, RULES, fill_pen=0.015)
            if o: r["res"][Lm] = {nm: o[nm]["pnl"] for nm in NAMES}
        if r["res"]: out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    hours = (res[-1]["bt"] - res[0]["bt"]) / 3600
    print(f"R1 (old data) S3 picks: {len(res)} launches over {hours:.1f} h (deployers {len(set(L[r['m']]['user'] for r in res))})")
    print(f"   {'exit':26}" + "".join(f"{'L' + str(x):>20}" for x in (0, 35, 45, 60, 75)))
    for nm in NAMES:
        cells = []
        for Lm in (0, 35, 45, 60, 75):
            v = [r["res"][Lm][nm] for r in res if Lm in r["res"]]; a = sum(r["res"][Lm][nm] for r in res if Lm in r["res"] and r["bt"] < mid)
            cells.append(f"{sum(v):+7.2f}({a:+.1f}/{sum(v) - a:+.1f})")
        print(f"   {nm:26}" + "".join(f"{c:>20}" for c in cells))
    json.dump(res, open("r1_s3.json", "w"))

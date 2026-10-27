#!/usr/bin/env python3
# print example lots with the tape from the trigger to the exit (who traded, sizes, the lot's return)
import sys, json, pickle, zlib, random, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
lots = json.load(open(f"{H.OUT}/lots.json"))
pf_sz = float(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 3; seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
sel = [l for l in lots if round(l["buy"]["sol"], 2) == pf_sz and l["closed"] and not l["censored"] and not l["brk"] and l["nlots"] == 1]
random.seed(seed); ex = random.sample(sel, n)
for l in ex:
    b = zlib.crc32(l["m"].encode()) % 64; d = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb"))[l["m"]]
    T = d["T"]; Wl = d["W"]; k = l["buy"]["k"]; q = float(T[k, 8]); cost = l["cost"] * 1e9
    ref = l["buy"]["s"] - (l["buy"]["trig_ds"] or 0)
    ex_s = l["sells"][-1]["s"]
    print(f"\n=== {l['m'][:8]} run {l['run']} buy {l['buy']['sol']} dip {l['buy']['dip']} trig {l['buy']['trig_sol']} age {l['buy']['age'] / 1000:.1f}s | sells at d={[x['s'] - ref for x in l['sells']]} parts {[round(x['part'], 2) for x in l['sells']]} | P&L {l['got'] - l['cost']:+.4f}")
    for j in range(max(0, k - 3), len(T)):
        s = int(T[j, 0])
        if s > ex_s + 2: break
        u = Wl[T[j, 5]]; fr = (T[j, 13] + T[j, 14]) / 1e4
        tag = "HAQQ" if u == H.W else ("ours" if u in H.US else ("HK" if u == H.HK else ("coh" if u in COH else u[:6])))
        v = T[j, 9] * q / (T[j, 10] + q) * (1 - fr) / cost - 1 if j >= k else float("nan")
        print(f"  d={s - ref:3d} i={T[j, 1]:4d} {'BUY ' if T[j, 6] else 'SELL'} {T[j, 7] / 1e9:7.3f} {tag:7s} vsol {T[j, 9] / 1e9:6.2f} lotret {v:+.3f}")

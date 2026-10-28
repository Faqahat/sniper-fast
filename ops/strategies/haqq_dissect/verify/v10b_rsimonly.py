#!/usr/bin/env python3
"""VERIFY v10b: the windows only rsim fills on the fresh tape - when (slots after the dump) and why my model never fills them."""
import sys, pickle, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V, v2b_reimpl as M
D = "/home/moiz/sniper-data/haqq_dissect/verify"
A = pickle.load(open(f"{D}/fwdF_res.pkl", "rb")); name = A["cfg"]["name"]; B = pickle.load(open(f"{D}/v2b_freshF.pkl", "rb"))
COST = M.COST
mine_f = collections.Counter((r["mint"], r["s"]) for r in B["rows"] if r["fill"] is not None)
mine_w = {(r["mint"], r["s"]) for r in B["rows"]}
info = collections.defaultdict(list)
for d, rows in enumerate(A["out"][name]):
    for r in rows:
        k = r[0]
        if k[0] != "re" or not r[1] or not r[3]: continue
        key = (k[1], k[2] - 3)
        if mine_f.get(key): continue
        info[key].append((d, r[8][0] - key[1], (r[8][2]["base"][0] - COST) / 1e6, r[2], k[5]))
tab = f"{D}/tab"; C = json.load(open(f"{tab}/creates.json"))
tp = V.Tape(tab, {k[0] for k in info})
for key, v in sorted(info.items(), key=lambda x: -sum(y[2] for y in x[1])):
    X = tp.rows(key[0]); c = C.get(key[0], {})
    s0 = c.get("slot"); 
    print(key[0][:8], "dump slot", key[1], "age_slots", key[1] - s0 if s0 else None, "in mine:", key in mine_w, "| rsim fills (draw, slots after dump, mSOL, why, stop):", [(a, b, round(cc, 1), w) for a, b, cc, w, _ in v][:5], "stop", v[0][4])

#!/usr/bin/env python3
# Parity data for the Rust port (src/dip.rs): a sample of launches with their trade tapes (as rp.read_bucket + repair gives
# them), structure (g_end, insiders, glued), and for every dip event the Python features (dipcv.fv order) and the frozen
# DIP4 scores. -> /home/moiz/sniper/testdata/dip_parity.json
import sys, os, json, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"; os.environ["DIP_LATS"] = "35"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import numpy as np
import dipbuy4 as D
from dipcv import FK, fv
import gbdt_np as G
M = json.load(open("/home/moiz/sniper/ops/overnight/dip/frozen_dip4_L35.json"))
def score(model, X):
    Bm = np.zeros(X.shape, np.int16)
    for j in range(X.shape[1]):
        b = np.searchsorted(np.array(model["edges"][j]), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
    f = np.full(len(X), model["F0"])
    for t in model["trees"]: f += model["lr"] * G.pred(t, Bm)
    return f
keys = sorted(D.byb)[:6]          # a few buckets
out = []
for key in keys:
    run, b = key
    tra = D.rp.read_bucket(run, b, D.byb[key])
    evs, _ = D.work(key)
    byev = collections.defaultdict(list)
    for e in evs: byev[e["m"]].append(e)
    for m, tr in tra.items():
        if m not in byev: continue
        c = D.L[m]; st = D.rp.structure(tr, c)
        X = np.array([fv(e) for e in byev[m]]); sc = score(M, X)
        # event index k: the sell whose age matches (first matching non-synthetic sell >= 1 SOL)
        S = c["slot"]; ks = []
        for e in byev[m]:
            k = next(k for k, t in enumerate(tr) if (not t["buy"]) and not t.get("syn") and t["sol"] >= 1e9 and k >= st["g_end"] and round((t["s"] - S) * D.SMS / 1000, 2) == e["age"])
            ks.append(k)
        out.append(dict(mint=m, slot=S, g_end=st["g_end"], insiders=sorted(u for u in st["insiders"] if u), glued=len(st["glued"]),
                        trades=[[t["s"], t["i"], t["user"], int(t["buy"]), t["sol"], t["tok"], t["vsol"], t["vtok"], int(bool(t.get("syn")))] for t in tr],
                        events=[dict(k=k, feats=[float(x) for x in X[i]], score=float(sc[i])) for i, k in enumerate(ks)]))
    if len(out) >= 60: break
json.dump(dict(features=FK, model="frozen_dip4_L35.json", launches=out), open("/home/moiz/sniper/testdata/dip_parity.json", "w"))
print("launches", len(out), "events", sum(len(x["events"]) for x in out))

#!/usr/bin/env python3
# READ-ONLY, offline: the walk-forward CWiNFA deployer list (+ gate) on the OLDER run R1 (no engine timelines: block-position
# proxy placement, pessimistic) - an out-of-sample check of question 6 (b). Same rules as q6.py.
import os, sys, json, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); R = json.load(open(os.path.join(HERE, "replay_all.json"))); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
def walk(Lm, run, k=2, rate=0.10, gate=True, kmin=3, thr=0.0):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
    natt = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; picks = []
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]; r = R.get(m)
        listed = natt[d] >= k and (nl[d] == 0 or natt[d] / nl[d] >= rate)
        gok = not (gate and len(hist[d]) >= kmin and statistics.mean(hist[d]) < thr)
        if r and r["run"] == run and str(Lm) in r and listed and gok: picks.append(m)
        if r and str(Lm) in r and r[str(Lm)]["ok"] and r[str(Lm)].get("eos05") is not None: pend.append((bt + 60, d, r[str(Lm)]["eos05"])); pend.sort()
        nl[d] += 1
        if m in ATT: natt[d] += 1
    return picks
out = {}
for Lm in (45, 75):
    for name, kw in (("oracle (its attempts)", None), ("list, no gate", dict(gate=False)), ("list + gate", dict())):
        P = [m for m, r in R.items() if r["run"] == "R1" and m in ATT] if kw is None else walk(Lm, "R1", **kw)
        for key in ("eos05", "cw10"):
            v = sorted((R[m]["bt"], (R[m][str(Lm)].get(key) if R[m][str(Lm)]["ok"] else -0.005)) for m in P if str(Lm) in R[m] and (not R[m][str(Lm)]["ok"] or R[m][str(Lm)].get(key) is not None))
            tot = sum(x for _, x in v); mid = v[0][0] + (v[-1][0] - v[0][0]) / 2 if v else 0; a = sum(x for t, x in v if t < mid)
            f = sum(1 for _, x in v if x != -0.005)
            out[f"R1_{Lm}_{name}_{key}"] = dict(tot=round(tot, 3), h1=round(a, 3), h2=round(tot - a, 3), fills=f, n=len(v))
            print(f"R1 (proxy) L{Lm} {name:22} {key:5}: {tot:+6.2f} SOL ({a:+.2f}/{tot - a:+.2f}) fills {f}/{len(v)}")
json.dump(out, open(os.path.join(HERE, "q6_r1.json"), "w"), indent=1)

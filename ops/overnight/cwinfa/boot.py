#!/usr/bin/env python3
# READ-ONLY, offline: bootstrap of the walk-forward CWiNFA list + gate result (question 6b), R2 replay window.
import os, sys, json, random, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); R = json.load(open(os.path.join(HERE, "replay_all.json"))); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
def walk(Lm, k=2, rate=0.10, kmin=3, thr=0.0):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
    natt = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; picks = []
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]; r = R.get(m)
        if r and r["run"] == "R2" and str(Lm) in r and natt[d] >= k and (nl[d] == 0 or natt[d] / nl[d] >= rate) and not (len(hist[d]) >= kmin and statistics.mean(hist[d]) < thr): picks.append(m)
        if r and str(Lm) in r and r[str(Lm)]["ok"] and r[str(Lm)].get("eos05") is not None: pend.append((bt + 60, d, r[str(Lm)]["eos05"])); pend.sort()
        nl[d] += 1
        if m in ATT: natt[d] += 1
    return picks
random.seed(7); out = []
for Lm in (45, 75):
    P = walk(Lm)
    for key in ("eos05", "cw10"):
        v = [(R[m][str(Lm)].get(key) if R[m][str(Lm)]["ok"] else -0.005) for m in P if (not R[m][str(Lm)]["ok"]) or R[m][str(Lm)].get(key) is not None]
        bs = sorted(sum(random.choice(v) for _ in v) for _ in range(4000))
        out.append(f"L{Lm} list+gate {key}: total {sum(v):+.2f} SOL, bootstrap 5-95% [{bs[200]:+.2f}, {bs[3800]:+.2f}], P(total <= 0) {sum(b <= 0 for b in bs) / len(bs):.3f}, n {len(v)}")
open(os.path.join(HERE, "boot.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))

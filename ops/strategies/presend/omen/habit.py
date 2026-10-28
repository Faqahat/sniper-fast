#!/usr/bin/env python3
"""OMEN step 1b: causal per-wallet habit features at every position open and every dump. CENS = censor hold at 150 slots.
Out: hab.pkl with per position: n_prior, med, iqr, p30 (share of prior positions first-sold within 30 slots), pbig (share of prior
positions whose first sell sold >= 50%), plus the outcome. Wallet history uses only positions whose outcome was known before the moment."""
import pickle, collections, heapq, sys
import numpy as np
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
CENS = 150
P = []; DU = []
for D in range(7):
    Z = pickle.load(open(f"{W}/pos_D{D}.pkl", "rb")); P += Z["P"]; DU += Z["DU"]
for p in P:
    h = (p["fs"] - p["s"]) if "fs" in p else None
    p["hold"] = h if (h is not None and h <= CENS) else CENS + 1
    p["known"] = p["s"] + min(p["hold"], CENS + 1)
    p["big"] = ("fs" in p and p["hold"] <= CENS and p.get("frac", 0) >= 0.5)
# events: position opens (query) and position outcomes known (update), in slot order; updates at slot <= query slot - 1 count
ev = []
for q, p in enumerate(P):
    ev.append((p["s"], 1, q)); ev.append((p["known"], 3, q))
for q, d in enumerate(DU): ev.append((d["s"], 2, q))
ev.sort()
hist = collections.defaultdict(list)
def feats(w):
    H = hist.get(w)
    if not H: return dict(n=0)
    a = np.array([x[0] for x in H]); b = np.array([x[1] for x in H])
    q25, q50, q75 = np.percentile(a, [25, 50, 75])
    return dict(n=len(a), med=float(q50), iqr=float(q75 - q25), p30=float((a <= 30).mean()), pbig=float(b.mean()),
                pbig30=float(((a <= 30) & b).mean()), last=a[-10:].tolist())
for s, kind, q in ev:
    if kind == 3:
        p = P[q]; hist[p["w"]].append((p["hold"], p["big"]))
    elif kind == 1:
        P[q]["f"] = feats(P[q]["w"])
    else:
        DU[q]["f"] = feats(DU[q]["w"])
pickle.dump(dict(P=P, DU=DU), open(f"{W}/hab.pkl", "wb"))
print(len(P), len(DU))

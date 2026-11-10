#!/usr/bin/env python3
"""FLATSIG step: fit BOTSEL on DEV chain triggers; report AUC on DEV / later chain (HOLD span); then score OUR DEV T2 positions
by the model and show P&L / flat share per score bin. Writes the fitted model to flatsig/botsel_model.json."""
import pickle, numpy as np, sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L, fmodel as FM, fpos
T = pickle.load(open(f"{L.D}/trig.pkl", "rb")); X = T["X"]; M = T["meta"]; C = T["cols"]; ci = {c: i for i, c in enumerate(C)}
bt = np.array([m["bt"] for m in M]); dip = np.array([m["dip"] for m in M]); span = np.array([m["in_span"] for m in M])
uni = span & dip & (X[:, ci["age"]] >= 2) & (X[:, ci["vsol_pre"]] >= 28) & (X[:, ci["sol"]] >= 1)
lab = sys.argv[1] if len(sys.argv) > 1 else "dC2"
y = np.array([m.get(lab, 0) > 0 for m in M]).astype(float)
dev = uni & (bt < L.CUT / 1e9); late = uni & (bt >= L.CUT / 1e9)
rows = [dict(zip(C, X[k])) for k in range(len(M))]
XD = FM.transform([rows[k] for k in np.nonzero(dev)[0]])
m = FM.fit(XD, y[dev])
sD = FM.score(m, XD); XL = FM.transform([rows[k] for k in np.nonzero(late)[0]]); sL = FM.score(m, XL)
print(lab, "DEV n", dev.sum(), "rate", y[dev].mean().round(3), "AUC", round(FM.auc(sD, y[dev]), 3), "| later n", late.sum(), "rate", y[late].mean().round(3), "AUC", round(FM.auc(sL, y[late]), 3))
names = []
for c in FM.FEATS: names += [c, c + "_nohist"] if c in FM.RATE else [c]
for nme, w in sorted(zip(names, m["w"][1:]), key=lambda x: -abs(x[1]))[:14]: print(f"   {nme:16s} {w:+.3f}")
json.dump({**m, "label": lab, "feats": FM.FEATS, "names": names}, open(f"{L.D}/botsel_model_{lab}.json", "w"))
P = [p for p in fpos.positions() if "f" in p and p["kind"] == "T2" and not p["q3a"]]
for per in ["DEV", "VAL", "HOLD"]:
    Q = [p for p in P if p["per"] == per]
    if not Q: continue
    s = FM.score(m, FM.transform([p["f"] for p in Q]))
    qs = np.quantile(s, [0, .1, .2, .3, .5, .7, 1]) if per == "DEV" else qs
    out = []
    for lo, hi in zip(qs[:-1], qs[1:]):
        mm = (s >= lo) & (s < hi) if hi != qs[-1] else (s >= lo)
        b = [p for p, k in zip(Q, mm) if k]; c = collections.Counter(p["cls"] for p in b)
        if b: out.append(f"[{lo:.2f},{hi:.2f}) n{len(b)} {np.mean([p['pnl'] for p in b])*1000:+.1f} fl{c['flat']/len(b):.2f} w{c['win']/len(b):.2f}")
    print(per, len(Q), " | ".join(out))

#!/usr/bin/env python3
# MODEL CHECK step 6: per-wallet success curves S_w(p) = P(a buy lands | first landed tx at price ratio p vs the post-dump price),
# isotonic (non-increasing) fits on fresh attempts (att_<day>.npz). Target wallets with >= 300 attempts get their own curve; the
# other targets share the pooled target curve; non-target wallets get the pooled "others" curve.
# -> /home/moiz/sniper-data/modelcheck/curves_<tag>.json   (tag all = R1..R4, r12 = R1+R2 only, for an out-of-sample check)
import sys, os, json, zlib, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
OUT = "/home/moiz/sniper-data/modelcheck"
TG = [l.strip() for l in open(os.path.join(HERE, "targets.txt")) if l.strip()]
TGU = {zlib.crc32(w.encode()): w for w in TG}

def iso(x, y, nb=60):
    x = np.clip(x, 0.95, 1.6); o = np.argsort(x); x = x[o]; y = y[o]
    qs = np.unique(np.quantile(x, np.linspace(0, 1, nb + 1)))
    bi = np.clip(np.searchsorted(qs, x, side="right") - 1, 0, len(qs) - 2)
    cx = []; cy = []; w = []
    for k in range(len(qs) - 1):
        m = bi == k
        if m.any(): cx.append(float(x[m].mean())); cy.append(float(y[m].mean())); w.append(float(m.sum()))
    vals = cy[:]; wts = w[:]; idx = [[k] for k in range(len(cy))]; k = 0
    while k < len(vals) - 1:
        if vals[k] < vals[k + 1]:
            vals[k] = (vals[k] * wts[k] + vals[k + 1] * wts[k + 1]) / (wts[k] + wts[k + 1]); wts[k] += wts[k + 1]; idx[k] += idx[k + 1]
            del vals[k + 1], wts[k + 1], idx[k + 1]
            if k > 0: k -= 1
        else: k += 1
    fy = [0.0] * len(cy)
    for v, ii in zip(vals, idx):
        for i in ii: fy[i] = v
    return cx, fy

def build(days, tag):
    A = collections.defaultdict(list)
    for day in days:
        z = np.load(f"{OUT}/att_{day}.npz")
        for k in z.files: A[k].append(z[k])
    A = {k: np.concatenate(v) for k, v in A.items()}
    fresh = ~A["held"].astype(bool) & (A["age"] <= 1622)
    isT = np.isin(A["u"], np.array(list(TGU), np.int64)); ok = A["ok"].astype(float); r = A["ratio"]
    C = {"_targets": iso(r[fresh & isT], ok[fresh & isT]), "_others": iso(r[fresh & ~isT], ok[fresh & ~isT]), "_n": {}}
    cnt = collections.Counter(A["u"][fresh & isT].tolist())
    ta = A["tga"] > 0
    C["_targets|0"] = iso(r[fresh & isT & ~ta], ok[fresh & isT & ~ta]); C["_targets|1"] = iso(r[fresh & isT & ta], ok[fresh & isT & ta])
    for u, n in cnt.items():
        C["_n"][TGU[u]] = n
        if n >= 300:
            m = fresh & (A["u"] == u); C[TGU[u]] = iso(r[m], ok[m], nb=30 if n < 2000 else 60)
            for f_, nm in ((~ta, "|0"), (ta, "|1")):
                mm = m & f_
                if mm.sum() >= 150: C[TGU[u] + nm] = iso(r[mm], ok[mm], nb=20 if mm.sum() < 1500 else 40)
    json.dump(C, open(f"{OUT}/curves_{tag}.json", "w"))
    print(tag, "curves:", len(C) - 3, "wallets + pooled", flush=True)
    return C

if __name__ == "__main__":
    C = build(["R1", "R2", "R3", "R4"], "all"); build(["R1", "R2"], "r12")
    for w in ("HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "_targets", "_others"):
        cx, fy = C[w]; f = lambda p: float(np.interp(p, cx, fy))
        print(f"  {w[:8]:10s} S(1.00) {f(1.0):.2f} S(1.02) {f(1.02):.2f} S(1.05) {f(1.05):.2f} S(1.10) {f(1.10):.2f} S(1.20) {f(1.20):.2f}")

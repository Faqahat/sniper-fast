#!/usr/bin/env python3
"""VERIFY step 5 [MEASURED, read-only]: own per-mint trade tape for every live window mint (26 runs), from the decoded recorder tabs on
disjoint slot ranges (quiet3 chain, young ext, paper_audit tab, who tab_gap, multiarm tab38, tab_gap) + creates (creator per mint).
Out: /home/it/sniper-data/prevent/verify/tape.pkl {mints: {mint: dict of arrays}, users: [..], creates: {mint: (creator, slot)}}"""
import json, pickle, time, glob, os
import numpy as np
D = "/home/it/sniper-data"; OUT = f"{D}/prevent/verify"
SRC = [("chain", f"{D}/presend_quiet3", 0, 462709231), ("chain", f"{D}/presend_young/ext", 462709231, 462710488),
       ("tab", f"{D}/paper_audit/tab", 462710488, 463010350), ("tab", f"{D}/prevent/who/tab_gap", 463010350, 463021093),
       ("tab", f"{D}/multiarm/tab38", 463021093, 463049836), ("tab", f"{D}/prevent/who/tab_gap", 463049836, 1 << 40)]
CRE = sorted(glob.glob(f"{D}/haqq_dissect/rearm/tab_D*/creates.json")) + [f"{D}/omen3/d6/tab_D6/creates.json", f"{D}/omen3/tab_D7/creates.json",
      f"{D}/paper_audit/tab/creates.json", f"{D}/prevent/who/tab_gap/creates.json", f"{D}/multiarm/tab38/creates.json", f"{D}/presend_quiet4/tab37/creates.json"]
t0 = time.time()
T = pickle.load(open(f"{OUT}/tables.pkl", "rb"))
need = {w["mint"] for w in T["wins"] if w["mint"]}
print("mints needed", len(need), flush=True)
users = []; uid = {}
def U(s):
    k = uid.get(s)
    if k is None: k = uid[s] = len(users); users.append(s)
    return k
parts = {}
for kind, path, lo, hi in SRC:
    if kind == "chain":
        z = np.load(f"{path}/chain.npz"); I = json.load(open(f"{path}/ids.json")); ml, ul = I["mint"], I["user"]
        want = np.array([m in need for m in ml], bool)
        cm = z["mint"]; s = z["s"]
        sel = want[cm] & (s >= lo) & (s < hi); ix = np.nonzero(sel)[0]
        cols = dict(slot=s[ix].astype(np.int64), idx=z["i"][ix].astype(np.int64), j=z["j"][ix].astype(np.int64), buy=z["buy"][ix].astype(bool),
                    sol=z["sol"][ix].astype(np.int64), tok=z["tok"][ix].astype(np.int64), vsol=z["vsol"][ix].astype(np.int64), vtok=z["vtok"][ix].astype(np.int64))
        mm = [ml[g] for g in cm[ix].tolist()]; uu = [U(ul[g]) for g in z["user"][ix].tolist()]
        blocks = z["blocks"] if "blocks" in z.files else None
    else:
        A = np.load(f"{path}/trades.npy"); ids = json.load(open(f"{path}/ids.json"))
        want = np.array([m in need for m in ids], bool)
        sel = want[A["mint"]] & (A["slot"] >= lo) & (A["slot"] < hi); A = A[sel]
        cols = dict(slot=A["slot"].astype(np.int64), idx=A["idx"].astype(np.int64), j=A["j"].astype(np.int64), buy=A["buy"].astype(bool),
                    sol=A["sol"].astype(np.int64), tok=A["tok"].astype(np.int64), vsol=A["vsol"].astype(np.int64), vtok=A["vtok"].astype(np.int64))
        mm = [ids[g] for g in A["mint"].tolist()]; uu = [U(ids[g]) for g in A["user"].tolist()]
    cols["user"] = np.array(uu, np.int64)
    n = len(mm)
    order = {}
    for k, m in enumerate(mm): order.setdefault(m, []).append(k)
    for m, ks in order.items():
        ks = np.array(ks)
        parts.setdefault(m, []).append({c: v[ks] for c, v in cols.items()})
    print(path, lo, hi, "rows", n, "mints", len(order), f"{time.time()-t0:.0f}s", flush=True)
mints = {}
for m, ps in parts.items():
    a = {c: np.concatenate([p[c] for p in ps]) for c in ps[0]}
    o = np.lexsort((a["j"], a["idx"], a["slot"])); mints[m] = {c: v[o] for c, v in a.items()}
creates = {}
for p in CRE:
    if not os.path.exists(p): print("missing", p); continue
    c = json.load(open(p))
    for m, x in (c.items() if isinstance(c, dict) else ((y["mint"], y) for y in c)):
        if m in need and m not in creates: creates[m] = (x.get("creator") or x.get("user"), int(x["slot"]), x.get("user"))
print("mints with trades", len(mints), "of", len(need), "creates found", len(creates), f"{time.time()-t0:.0f}s", flush=True)
pickle.dump(dict(mints=mints, users=users, creates=creates), open(f"{OUT}/tape.pkl", "wb"))

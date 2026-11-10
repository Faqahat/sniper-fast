#!/usr/bin/env python3
"""TIMING step 2 [MEASURED, read-only]: every pump.fun curve trade of the wallet set W (t1 wallets.json: holders >= 2% at our fills /
signing / trigger, in-hold sellers >= 0.05 SOL, whales, creators of fill mints) across ALL tokens, 10-24 19:25 -> 10-30 03:55 PKT,
from the decoded tapes on disjoint slot ranges (WHO's list):
Out: /home/it/sniper-data/prevent/timing/hist.npz (slot, idx, j, bt, mint, user, buy, sol, tok, vsol, vtok; sorted user, slot, idx, j)
     + hist_ids.json (mint names, user names) + creates_all.pkl {mint: (creator, slot, bt, mayhem)}"""
import json, pickle, gc
import numpy as np
D = "/home/it/sniper-data"
OUT = f"{D}/prevent/timing"
# (haqq_dissect D0-D2 ids.json point to the archived dv8/tab -> not decodable by name: history starts 10-24 19:25 PKT)
SRC = [("chain", f"{D}/presend_quiet3", 460883340, 462709231),
       ("chain", f"{D}/presend_young/ext", 462709231, 462710488),
       ("tab", f"{D}/paper_audit/tab", 462710488, 463010350),
       ("tab", f"{D}/prevent/who/tab_gap", 463010350, 463021093),
       ("tab", f"{D}/multiarm/tab38", 463021093, 463049836),
       ("tab", f"{D}/prevent/who/tab_gap", 463049836, 463099999)]
Wn = json.load(open(f"{OUT}/wallets.json")); Wi = {u: k for k, u in enumerate(Wn)}
MINTS = []; Mi = {}
cols = {k: [] for k in ("slot", "idx", "j", "bt", "mint", "user", "buy", "sol", "tok", "vsol", "vtok")}
for kind, path, lo, hi in SRC:
    if kind == "chain":
        I = json.load(open(f"{path}/ids.json")); ml = I["mint"]; ul = I["user"]
        z = np.load(f"{path}/chain.npz")
        wid = np.array([k for k, u in enumerate(ul) if u in Wi], dtype=np.int64)
        u = z["user"]; s = z["s"]
        m = np.isin(u, wid) & (s >= lo) & (s < hi); sel = np.nonzero(m)[0]; del m
        uu = u[sel]; del u
        cols["slot"].append(s[sel].astype(np.int64)); del s
        cols["idx"].append(z["i"][sel].astype(np.int32)); cols["j"].append(z["j"][sel].astype(np.int16))
        cols["bt"].append(z["bt"][sel].astype(np.int64))
        cols["buy"].append(z["buy"][sel].astype(np.int8))
        for k in ("sol", "tok", "vsol", "vtok"): cols[k].append(z[k][sel].astype(np.int64))
        mm = z["mint"][sel]
        names_m = [ml[int(x)] for x in mm]; names_u = [ul[int(x)] for x in uu]
    else:
        T = np.load(f"{path}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{path}/ids.json"))
        wid = np.array([k for k, u in enumerate(ids) if u in Wi], dtype=np.int64)
        u = np.asarray(T["user"]); s = np.asarray(T["slot"])
        m = np.isin(u, wid) & (s >= lo) & (s < hi); sel = np.nonzero(m)[0]; del m
        t = np.asarray(T[sel])
        cols["slot"].append(t["slot"].astype(np.int64)); cols["idx"].append(t["idx"].astype(np.int32)); cols["j"].append(t["j"].astype(np.int16))
        cols["bt"].append(t["bt"].astype(np.int64)); cols["buy"].append(t["buy"].astype(np.int8))
        for k in ("sol", "tok", "vsol", "vtok"): cols[k].append(t[k].astype(np.int64))
        names_m = [ids[int(x)] for x in t["mint"]]; names_u = [ids[int(x)] for x in t["user"]]
        del u, s, T
    mk = np.empty(len(names_m), np.int32)
    for n, x in enumerate(names_m):
        g = Mi.get(x)
        if g is None: g = Mi[x] = len(MINTS); MINTS.append(x)
        mk[n] = g
    cols["mint"].append(mk); cols["user"].append(np.array([Wi[x] for x in names_u], np.int32))
    print(path.split("sniper-data/")[1], lo, hi, len(sel), flush=True)
    gc.collect()
A = {k: np.concatenate(v) for k, v in cols.items()}
o = np.lexsort((A["j"], A["idx"], A["slot"], A["user"]))
A = {k: v[o] for k, v in A.items()}
np.savez(f"{OUT}/hist.npz", **A)
json.dump({"mint": MINTS, "user": Wn}, open(f"{OUT}/hist_ids.json", "w"))
# creates: WHO's (D2 -> r38) + haqq D0/D1
CR = pickle.load(open(f"{D}/prevent/who/creates.pkl", "rb"))
pickle.dump(CR, open(f"{OUT}/creates_all.pkl", "wb"))
print("trades", len(A["slot"]), "mints", len(MINTS), "creates", len(CR))

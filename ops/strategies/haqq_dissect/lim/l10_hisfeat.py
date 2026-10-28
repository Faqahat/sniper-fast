#!/usr/bin/env python3
"""LIM step 10 (read-only): send-time features for haqq's DIP fills (data/lim/hrep.pkl) - same definitions as our fires
(l2): dump drop, dump SOL, curve SOL after the dump, token age (slots), seller type (dev / bundler / early / fbot / other),
trades in the dump's slot before the dump (nsame), trades / buy SOL in the 10 slots before the dump (n10, b10).
Out: data/lim/hfeat.pkl"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
H = [r for r in pickle.load(open(f"{OUT}/hrep.pkl", "rb")) if r.get("rep")]
ids, idm = L.ids_map(); fbid = {idm[w] for w in FB if w in idm}
T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
mids = np.array(sorted({idm[r["mint"]] for r in H}), np.uint32)
TT = np.asarray(T[np.isin(T["mint"], mids)]); TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
CR = json.load(open(f"{L.TAB}/creates.json")); CR = {m: CR[m] for m in {r["mint"] for r in H} if m in CR}
by = collections.defaultdict(list)
for r in H: by[r["mint"]].append(r)
for mint, bl in by.items():
    a, b = span[mint]; R = TT[a:b]
    sl = R["slot"].astype(np.int64); key = sl * 100000 + R["idx"].astype(np.int64); us = R["user"].astype(np.int64)
    bu = R["buy"].astype(bool); sol = R["sol"] / 1e9
    c = CR.get(mint) or {}; cs = c.get("slot"); cr_id = idm.get(c.get("creator"), -2) if c.get("creator") else -2
    bundl = set(us[(sl == cs) & bu].tolist()) if cs is not None else set()
    early = set(us[(sl <= cs + 10) & bu].tolist()) if cs is not None else set()
    for r in bl:
        k = int(np.searchsorted(key, r["d_slot"] * 100000 + r["d_idx"]))
        sel = int(us[k]) if k < len(us) else -1
        r["stype"] = "dev" if sel == cr_id else "bundler" if sel in bundl else "fbot" if sel in fbid else "early" if sel in early else "other"
        r["age"] = (r["d_slot"] - cs) if cs is not None else None
        r["mayhem"] = bool(c.get("mayhem"))
        w10 = (sl >= r["d_slot"] - 10) & (np.arange(len(sl)) < k); same = (sl == r["d_slot"]) & (np.arange(len(sl)) < k)
        r["n10"] = int(w10.sum()); r["b10"] = float(sol[w10 & bu].sum()); r["nsame"] = int(same.sum())
pickle.dump(H, open(f"{OUT}/hfeat.pkl", "wb")); print("done", len(H))

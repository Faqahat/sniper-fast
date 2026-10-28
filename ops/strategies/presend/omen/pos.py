#!/usr/bin/env python3
"""OMEN step 1 (read-only): every >=2% position (first buy that takes a wallet to >= 2% of supply on a token whose create is in
the tape) with its first sell after it, and every >= 1 SOL / >= 12%-drop dump. One tab = one PKT day (23:15 bounds).
usage: pos.py D TAB OUT.pkl"""
import sys, json, pickle, time
import numpy as np
DAY0 = 1793038500 - 5 * 86400
OUR = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
P2 = 20_000_000_000_000
def main(D, tab, out):
    t0 = time.time()
    T = np.load(f"{tab}/trades.npy"); ids = json.load(open(f"{tab}/ids.json")); cr = json.load(open(f"{tab}/creates.json"))
    idm = {k: v for v, k in enumerate(ids)}
    a_day = DAY0 + D * 86400; b_day = a_day + 86400
    o = np.lexsort((T["j"], T["idx"], T["slot"], T["user"], T["mint"])); T = T[o]
    mint = T["mint"].astype(np.int64); user = T["user"].astype(np.int64); buy = T["buy"].astype(bool)
    tok = T["tok"].astype(np.int64); sol = T["sol"].astype(np.int64); slot = T["slot"].astype(np.int64)
    vs = T["vsol"].astype(np.float64); vt = T["vtok"].astype(np.float64); bt = T["bt"].astype(np.int64); idx = T["idx"].astype(np.int64)
    n = len(T)
    g = np.concatenate([[True], (mint[1:] != mint[:-1]) | (user[1:] != user[:-1])])
    gid = np.cumsum(g) - 1; gstart = np.flatnonzero(g)
    sg = np.where(buy, tok, -tok); cs = np.cumsum(sg); base = np.concatenate([[0], cs[gstart[1:] - 1]])
    after = cs - base[gid]; before = after - sg
    # creates in tape
    cmint = {}; 
    for m, c in cr.items():
        if m in idm and not c.get("mayhem") and not c.get("mayhem_ix"): cmint[idm[m]] = (c["slot"], idm.get(c.get("creator"), -1), idm.get(c.get("user"), -1))
    hasc = np.array([int(m) in cmint for m in mint[gstart]])
    our = np.array([ids[int(u)] in OUR for u in user[gstart]])
    cross = np.flatnonzero(buy & (after >= P2) & (before < P2))
    _, first = np.unique(gid[cross], return_index=True); cross = cross[first]
    sells = np.flatnonzero(~buy)
    pre = (vs + sol) / np.maximum(vt - tok, 1); p = vs / np.maximum(vt, 1); drop = np.where(~buy, 1 - p / np.maximum(pre, 1e-30), 0.0)
    P = []
    for r in cross:
        gg = gid[r]
        if not hasc[gg] or our[gg]: continue
        if not (a_day <= bt[r] < b_day): continue
        m = int(mint[r]); s0, crt, sig = cmint[m]; u = int(user[r])
        q = np.searchsorted(sells, r, side="right"); fs = int(sells[q]) if q < len(sells) and gid[sells[q]] == gg else -1
        # first buy slot of the group (insider = bought in the create slot)
        fb = gstart[gg]
        rec = dict(D=D, w=ids[u], m=m, mint=ids[m], s=int(slot[r]), i=int(idx[r]), bt=int(bt[r]), pct=after[r] / 1e13, bpct=before[r] / 1e13,
                   vsol=vs[r], age=int(slot[r] - s0), creator=(u == crt or u == sig), insider=bool(slot[fb] == s0 and u != crt and u != sig),
                   sol_in=int(sol[r]))
        if fs >= 0:
            rec.update(fs=int(slot[fs]), fsi=int(idx[fs]), frac=tok[fs] / max(before[fs], 1), drop=drop[fs], fsol=int(sol[fs]))
            # first big dump (>=1 SOL, >=12% drop) by this wallet on this token after the crossing
            e = gstart[gg + 1] if gg + 1 < len(gstart) else n
            kk = np.arange(fs, e); kk = kk[(~buy[kk]) & (sol[kk] >= 1_000_000_000) & (drop[kk] >= 0.12)]
            if len(kk): rec.update(bd=int(slot[kk[0]]), bdi=int(idx[kk[0]]))
            # sold share by open+30 slots: balance at the last row of the group with slot <= s+30
            kk2 = np.arange(r, e); kk2 = kk2[slot[kk2] <= slot[r] + 30]
            rec["frac30"] = 1 - after[kk2[-1]] / max(after[r], 1)
        P.append(rec)
    # dumps
    dm = np.flatnonzero((~buy) & (sol >= 1_000_000_000) & (drop >= 0.12) & (bt >= a_day) & (bt < b_day))
    crossmap = {int(gid[r]): int(r) for r in cross}
    DU = []
    for k in dm:
        gg = int(gid[k])
        if not hasc[gg] or our[gg]: continue
        m = int(mint[k]); r = crossmap.get(gg)
        DU.append(dict(D=D, w=ids[int(user[k])], m=m, s=int(slot[k]), i=int(idx[k]), bt=int(bt[k]), sol=int(sol[k]), drop=float(drop[k]), vsol=vs[k],
                       pos_s=(int(slot[r]) if r is not None and r < k else None), first_sell=(r is not None and r < k and int(sells[np.searchsorted(sells, r, side='right')]) == k),
                       creator=int(user[k]) in (cmint[m][1], cmint[m][2])))
    pickle.dump(dict(P=P, DU=DU), open(out, "wb"))
    print(D, len(P), "positions", len(DU), "dumps", f"{time.time() - t0:.0f}s", flush=True)
if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3])

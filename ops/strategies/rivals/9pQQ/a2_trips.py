#!/usr/bin/env python3
"""9pQQ step 2: every round trip (it never scales in: one buy, one full sell) with entry + exit context from the full tape.
Net = buy lamports + sell lamports + token-account rent refunded later by CloseAccount (only when the buy created the account).
-> /home/moiz/sniper-data/rivals/9pQQ/trips_<run>.pkl (list of dicts).  Read-only on inputs.
usage: a2_trips.py [run ...]"""
import sys, pickle, collections, math
import numpy as np
import tlib9 as L

def feat_run(run):
    t = L.load_tape(run)
    own = L.own(run)
    la = L.launches(run)
    wid = t.user_ix.get(L.W, -1)
    oid = t.user_ix.get(L.OURS, -1)
    # trade counts per user (bot-ness)
    ucnt = np.bincount(t.u, minlength=len(t.users))
    # rent per created account: the account-creating buys (InitializeAccount3) pay it; CloseAccount refunds it
    cl = [x for x in own if x["kind"] == "close"]          # refund per closed account, measured from the CloseAccount txs
    RENT = int(sum(x["sol"] for x in cl) / max(1, sum(len(x["ixn"]) for x in cl)))
    seq = collections.defaultdict(list)
    for x in own:
        if x["kind"] in ("buy", "sell"): seq[x["mint"]].append(x)
    trips = []
    for m, v in seq.items():
        mi = t.mint_ix.get(m)
        k = 0; j = 0
        while j < len(v):
            if v[j]["kind"] != "buy": j += 1; continue
            b = v[j]; s_ = v[j + 1] if j + 1 < len(v) and v[j + 1]["kind"] == "sell" else None
            k += 1
            tr = dict(run=run, mint=m, k=k, bs=b["s"], bi=b["i"], bbt=b["bt"], bsig=b["sig"], spend=-b["sol"], tok=b["tok"],
                      created="InitializeAccount3" in b["ixn"], bcup=b["cup"], btips=b["tips"], bfee=b["fee"])
            if s_:
                tr.update(ss=s_["s"], si=s_["i"], sbt=s_["bt"], ssig=s_["sig"], proceeds=s_["sol"], sfee=s_["fee"], stips=s_["tips"],
                          stok=-s_["tok"])
                tr["net"] = b["sol"] + s_["sol"] + (RENT if tr["created"] else 0)
                tr["hold"] = s_["s"] - b["s"]
            else:
                tr["net"] = None; tr["hold"] = None
            if j > 0 and v[j - 1]["kind"] == "sell":
                tr["prev_sell_s"] = v[j - 1]["s"]; tr["prev_net"] = trips[-1]["net"] if trips and trips[-1]["mint"] == m else None
            L_ = la.get(m)
            tr["age"] = b["s"] - L_["slot"] if L_ else None
            tr["may"] = L_["may"] if L_ else None
            tr["creator"] = L_["creator"] if L_ else None
            if mi is not None: ctx(t, mi, tr, wid, oid, ucnt)
            trips.append(tr)
            j += 2 if s_ else 1
    return trips, RENT

def ctx(t, mi, tr, wid, oid, ucnt):
    a0, a1 = t.mstart[mi], t.mstart[mi + 1]
    S, I, U, TOK, SOL, CP, CQ = t.s[a0:a1], t.i[a0:a1], t.u[a0:a1], t.tok[a0:a1], t.sol[a0:a1], t.cpre[a0:a1], t.cpost[a0:a1]
    key = S * 10000 + I
    jb = int(np.searchsorted(key, tr["bs"] * 10000 + tr["bi"]))
    if jb >= len(S) or U[jb] != wid: tr["tape_ok"] = False; return
    tr["tape_ok"] = True
    tr["ntr_before"] = jb                                    # trades on this mint earlier in the recording
    tr["first_s"] = int(S[0])
    cb = CP[jb]; tr["cbal"] = int(cb)
    tr["vsol"] = L.vsol(cb) / 1e9
    tr["prog"] = (1000e12 - cb) / 793.1e12
    pb = L.price(cb); pa = L.price(CQ[jb])
    tr["impact"] = pa / pb - 1
    others = U != wid
    bs = tr["bs"]
    k0 = int(np.searchsorted(S, bs - 450))
    sS, sU, sT, sL, sC = S[k0:jb], U[k0:jb], TOK[k0:jb], SOL[k0:jb], CP[k0:jb]
    so = sU != wid
    for w in (0, 1, 3, 10, 25, 75, 150, 450):
        sel = (sS >= bs - w) & so
        b_ = sel & (sT > 0); s_ = sel & (sT < 0)
        tr[f"bsol{w}"] = float(-sL[b_].sum() / 1e9); tr[f"ssol{w}"] = float(sL[s_].sum() / 1e9)
        tr[f"nb{w}"] = int(b_.sum()); tr[f"ns{w}"] = int(s_.sum())
        tr[f"nbu{w}"] = int(len(np.unique(sU[b_])))
        q = int(np.searchsorted(sS, bs - w))
        tr[f"dp{w}"] = pb / L.price(sC[q]) - 1 if q < len(sS) else 0.0
    def win(lo, hi, jhi):                                    # others' trades in slots [lo, hi], before index jhi
        sel = np.zeros(len(S), bool); a = int(np.searchsorted(S, lo)); sel[a:jhi] = True
        sel &= (S <= hi) & others
        return sel
    if k0 < jb:
        cs = CQ[k0:jb]; tr["dd450"] = pb / L.price(cs.min()) - 1; tr["ru450"] = pb / L.price(cs.max()) - 1
    else: tr["dd450"] = tr["ru450"] = 0.0
    # last other trade before the buy
    pj = jb - 1
    while pj >= 0 and U[pj] == wid: pj -= 1
    if pj >= 0:
        tr["last_side"] = 1 if TOK[pj] > 0 else -1; tr["last_sol"] = abs(SOL[pj]) / 1e9; tr["last_gap"] = int(bs - S[pj])
        tr["last_ix"] = int(tr["bi"] - I[pj]) if S[pj] == bs else None
        tr["last_bot"] = int(ucnt[U[pj]])
        tr["last_user"] = str(t.users[U[pj]])
    # biggest other sell in [bs-3, bs] before the buy
    sel = win(bs - 3, bs, jb) & (TOK < 0)
    if sel.any():
        q = np.where(sel)[0][np.argmax(SOL[sel])]
        tr["dump_sol"] = SOL[q] / 1e9; tr["dump_gap"] = int(bs - S[q]); tr["dump_drop"] = 1 - L.price(CQ[q]) / L.price(CP[q])
        tr["dump_ix"] = int(tr["bi"] - I[q]) if S[q] == bs else None
        tr["dump_user"] = str(t.users[U[q]]); tr["dump_bot"] = int(ucnt[U[q]])
        tr["dump_share"] = -TOK[q] / 1e15
    # biggest other buy in [bs-3, bs]
    sel = win(bs - 3, bs, jb) & (TOK > 0)
    if sel.any():
        q = np.where(sel)[0][np.argmax(-SOL[sel])]
        tr["pump_sol"] = -SOL[q] / 1e9; tr["pump_gap"] = int(bs - S[q])
    # holder structure at the buy: net token holdings of others from the recorded tape (only valid if launch is inside the recording)
    if tr.get("age") is not None:
        uq, inv = np.unique(U[:jb], return_inverse=True)
        hv = np.bincount(inv, weights=TOK[:jb].astype(float), minlength=len(uq)) if jb else np.zeros(0)
        hold = dict(zip(uq.tolist(), hv.tolist()))
        hs = sorted((x for x in hv.tolist() if x > 0), reverse=True)
        tr["holders"] = len(hs); tr["top1"] = hs[0] / 1e15 if hs else 0; tr["top5"] = sum(hs[:5]) / 1e15 if hs else 0
        cr = tr.get("creator")
        cu = t.user_ix.get(cr) if cr else None
        tr["dev_hold"] = hold.get(cu, 0) / 1e15 if cu is not None else None
        tr["dev_sold"] = bool(cu is not None and ((U[:jb] == cu) & (TOK[:jb] < 0)).any())
    tr["ours_buy_before"] = bool(((U[:jb] == oid) & (TOK[:jb] > 0) & (S[:jb] >= bs - 10)).any()) if oid >= 0 else False
    if "ss" not in tr: return
    js = int(np.searchsorted(key, tr["ss"] * 10000 + tr["si"]))
    if js >= len(S) or U[js] != wid: return
    tr["ours_buy_during"] = bool(((U[jb:js] == oid) & (TOK[jb:js] > 0)).any()) if oid >= 0 else False
    ps = L.price(CP[js])
    pfill = L.price(CQ[jb])                                  # curve price right after its buy
    tr["exit_move"] = ps / pfill - 1                          # curve price at its sell vs right after its buy
    seg = slice(jb + 1, js)
    cq = CQ[seg]
    if len(cq):
        tr["mfe"] = L.price(cq.min()) / pfill - 1; tr["mae"] = L.price(cq.max()) / pfill - 1
        oth = U[seg] != wid
        tr["hold_nb"] = int(((TOK[seg] > 0) & oth).sum()); tr["hold_ns"] = int(((TOK[seg] < 0) & oth).sum())
        tr["hold_bsol"] = float(-SOL[seg][(TOK[seg] > 0) & oth].sum() / 1e9); tr["hold_ssol"] = float(SOL[seg][(TOK[seg] < 0) & oth].sum() / 1e9)
        # time of the peak inside the hold
        kpk = int(np.argmin(cq)); tr["peak_slot"] = int(S[jb + 1 + kpk] - tr["bs"])
    else:
        tr["mfe"] = tr["mae"] = 0.0; tr["hold_nb"] = tr["hold_ns"] = 0; tr["hold_bsol"] = tr["hold_ssol"] = 0.0; tr["peak_slot"] = None
    tr["hold_trades"] = int(js - jb - 1)
    # what came right before its sell (others)
    pj = js - 1
    while pj > jb and U[pj] == wid: pj -= 1
    if pj > jb:
        tr["xlast_side"] = 1 if TOK[pj] > 0 else -1; tr["xlast_sol"] = abs(SOL[pj]) / 1e9; tr["xlast_gap"] = int(tr["ss"] - S[pj])
        tr["xlast_user"] = str(t.users[U[pj]]); tr["xlast_bot"] = int(ucnt[U[pj]])
        tr["xlast_ix"] = int(tr["si"] - I[pj]) if S[pj] == tr["ss"] else None
    else: tr["xlast_side"] = 0
    # big sell by another wallet in the 3 slots before its sell (and inside the hold)
    a = max(jb + 1, int(np.searchsorted(S, tr["ss"] - 3)))
    sel = (TOK[a:js] < 0) & (U[a:js] != wid)
    tr["xdump_sol"] = float(SOL[a:js][sel].max() / 1e9) if sel.any() else 0.0
    # quiet time: slots since the last other trade before its sell
    # next other trade after its sell
    nj = js + 1
    while nj < len(S) and U[nj] == wid: nj += 1
    if nj < len(S):
        tr["nx_side"] = 1 if TOK[nj] > 0 else -1; tr["nx_sol"] = abs(SOL[nj]) / 1e9; tr["nx_gap"] = int(S[nj] - tr["ss"])
        tr["nx_user"] = str(t.users[U[nj]]); tr["nx_bot"] = int(ucnt[U[nj]])
    # price path after its exit (what it left on the table): price 25 / 150 slots after the sell vs its sell price
    for w in (25, 150):
        k1 = int(np.searchsorted(S, tr["ss"] + w, side="right")) - 1
        tr[f"after{w}"] = L.price(CQ[k1]) / L.price(CQ[js]) - 1 if k1 > js else 0.0
    # did OUR wallet sell inside its hold / did it sell into our hold
    if oid >= 0:
        tr["ours_sell_during"] = bool(((U[seg] == oid) & (TOK[seg] < 0)).any())

if __name__ == "__main__":
    runs = sys.argv[1:] or L.RUNS
    for r in runs:
        trips, RENT = feat_run(r)
        pickle.dump(trips, open(f"{L.OUT}/trips_{r}.pkl", "wb"))
        c = [x for x in trips if x["net"] is not None]
        print(r, "trips", len(trips), "closed", len(c), "rent", RENT, "net", round(sum(x["net"] for x in c) / 1e9, 2),
              "tape_ok", sum(1 for x in trips if x.get("tape_ok")), flush=True)

#!/usr/bin/env python3
"""SELLID step 5 (read-only): exact-replay paths of OUR live fills (same set and logic as exit/x6_ourpaths.py: sellland.pkl, actual
entry, our two wallets removed after the entry, 300 slots), PLUS the user id of every outside row (needed for wallet-trigger exits).
Out: sellid/ourpaths_us.pkl"""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
HZ = 300


def main():
    R, MI, span, CC = X.tape()
    ours = [MI["who"]["FRA"], MI["who"]["AMS"]]
    S = pickle.load(open(f"{X.OUT}/sellland.pkl", "rb"))
    out = []
    for r in S:
        if "realized" not in r: continue
        M = X.Mint(r["mint"]); k = min(r["bk"])
        o = ~np.isin(M.us, ours)
        hi = int(np.searchsorted(M.sl, M.sl[k] + HZ, side="right"))
        js = np.flatnonzero(o[k + 1:hi]) + k + 1
        fee = M.fee[k] if M.fee[k] > 0 else X.FEE
        p = dict(kind=r["kind"], run=r["run"], srv=r["srv"], mint=r["mint"], day=r["day"], bt=r["bt"], why=r["why"], hold=r["hold"], tp=r["tp"], sl=r["sl"],
                 V0=float(M.vsp[k]), T0=float(M.vtp[k]), sin=float(M.so[k]), tok=float(M.tk[k]), cost=float(M.so[k] * (1 + fee)), fee=float(fee),
                 b_slot=int(M.sl[k]), b_idx=int(M.ix[k]), b_cc=float(M.cc[k]), off_in_slot=float(M.cc[k] - M.sl[k] * X.SMS),
                 dcc=(M.cc[js] - M.cc[k]).astype(np.float64), dsl=(M.sl[js] - M.sl[k]).astype(np.int64), bu=M.bu[js].copy(), so=M.so[js].copy(),
                 tk=M.tk[js].copy(), us=M.us[js].astype(np.int64), ix=M.ix[js].astype(np.int64), realized=r["realized"], got=r["got"], s_k=r["s_k"], s_slot=r["s_slot"],
                 sell_rows_before=int(np.searchsorted(js, r["s_k"])), nsell=len(r["sk"]), react_ms=r.get("react_ms"), timer_ms=r.get("timer_ms"),
                 timer_slots=r.get("timer_slots"), spend=r["spend"])
        p["sells"] = [(int(np.searchsorted(js, kk)), float(M.tk[kk])) for kk in r["sk"]]
        out.append(p)
    pickle.dump(out, open("/home/moiz/sniper-data/haqq_dissect/sellid/ourpaths_us.pkl", "wb"))
    print("positions", len(out))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""VERIFY v5: end-to-end check of MY replay model (v2b: transplanted live try streams + limit rule + own exit) on the LIVE T2
windows of FRA r26/r27 inside the fresh tape (ground truth). Each live window: armed from its trigger chain clock + 50 ms until
its live end (expired: end of en_slot; whale_sold/quiet: the disarm's engine slot start + 100 ms; filled: the would-be end =
min(end of en_slot, the whale's first later sell + 50 ms)). One position at a time as live. Model P&L at 0.40 SOL is scaled x1.125
to the live 0.45 SOL. Compared with the live fills and the wallet-realized P&L (presend_live_realized) of the same windows.
usage: v5_validate.py [--seeds 10]"""
import sys, json, pickle, collections, argparse
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V
import v2b_reimpl as M

DATA = "/home/moiz/sniper-data/haqq_dissect/verify"
SMS = V.SMS

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, default=10); A = ap.parse_args()
    runs = {"r26": "/home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl", "r27": f"{DATA}/live/dip_r27.jsonl"}
    W = []; real = {}; fills = {}
    for rn, fn in runs.items():
        cur = {}
        for r in V.load_runs([fn]):
            ev = r.get("ev")
            if ev == "presend_live_arm": cur[r["trig"]["mint"]] = dict(run=rn, trig=r["trig"], en=r["en_slot"])
            elif ev == "presend_live_disarm" and r["mint"] in cur:
                w = cur.pop(r["mint"]); w.update(why=r["why"], dslot=r["slot"], filled=r.get("filled")); W.append(w)
            elif ev == "presend_live_fill": fills[(rn, r["mint"])] = r
            elif ev == "presend_live_realized": real[(rn, r["mint"])] = real.get((rn, r["mint"]), 0) + r["pnl"] / 1e9
    mints = {w["trig"]["mint"] for w in W}
    tp = V.Tape(f"{DATA}/tab", mints)
    S = np.load(f"{DATA}/tab/slots.npy"); BTE = int(S["bt"].max()) - 90
    lander = M.Lander(M.donor_streams("/home/moiz/sniper-data/dv8/tab"))
    rows = []
    for w in W:
        t = w["trig"]; s = int(t["slot"])
        if not (s >= tp.s0 + 100 and tp.bt_of(s) > M.FRESH0 and tp.bt_of(s) < BTE): continue
        X = tp.rows(t["mint"])
        if X is None: continue
        ours = np.isin(X["signer"], list(tp.our)) | np.isin(X["user"], list(tp.our))
        X = X[~ours]
        if not len(X): continue
        cc = np.array([tp.cc(int(a), int(b)) for a, b in zip(X["slot"], X["idx"])])
        t_arm = tp.cc(s, int(t["idx"])) + 50.0
        end = (w["en"] + 1) * SMS
        if w["why"] in ("whale_sold", "quiet"): end = w["dslot"] * SMS + 100.0
        elif w["why"] == "filled":
            wid = tp.idm.get(t["wallet"])
            sells = np.flatnonzero((X["user"] == wid) & (X["buy"] == 0) & (cc > t_arm - 50))
            if len(sells): end = min(end, cc[sells[0]] + 50.0)
        rows.append(dict(w=w, X=X, cc=cc, t_arm=t_arm, end=end, en=w["en"]))
    rows.sort(key=lambda r: r["t_arm"])
    print(f"live windows in the fresh tape: {len(rows)}; live fills there: {sum(1 for r in rows if r['w']['filled'])}; "
          f"live realized on them {sum(real.get((r['w']['run'], r['w']['trig']['mint']), 0) for r in rows if r['w']['filled']):+.3f} SOL")
    res = []; DIAG = collections.Counter(); LW = collections.Counter((r['w']['why'], bool(r['w']['filled'])) for r in rows); DT = []
    for sd in range(A.seeds):
        rng = np.random.default_rng(100 + sd); busy = -1.0; nf = 0; pnl = 0.0; fees = 0; both = 0
        for r in rows:
            X, cc = r["X"], r["cc"]; price = X["vsol"] / np.maximum(X["vtok"], 1)
            t0 = max(r["t_arm"], busy); t1 = r["end"]
            if t1 <= t0: continue
            got = False
            for L, s2 in lander.stream(rng, t0, t1 + 120.0):
                if L - s2 + 15.0 >= t1 or L >= (r["en"] + 1) * SMS: continue
                kb = int(np.searchsorted(cc, L, side="left")) - 1; kv = int(np.searchsorted(cc, L - s2, side="right")) - 1
                if kb < 0 or kv < 0: fees += 5120; continue
                if price[kb] <= 0.88 * price[kv] and X["vsol"][kb] < 100e9:
                    s_in = int(L // SMS); ex = M.exits(X, cc, kb, L, s_in)
                    nf += 1; pnl += 1.125 * (ex["live"] - M.COST) / 1e9; got = True
                    both += int(bool(r["w"]["filled"])); DIAG[(r['w']['why'], bool(r['w']['filled']))] += 1; DT.append((r['w']['why'], t1 - L, L - r['t_arm']))
                    busy = max(L + 1059.0, (s_in + 2) * SMS + 100.0) + 60.0
                    break
                fees += 5120
        res.append((nf, pnl, fees / 1e9, both))
    R = np.array(res)
    live_f = sum(1 for r in rows if r["w"]["filled"]); live_p = sum(real.get((r["w"]["run"], r["w"]["trig"]["mint"]), 0) for r in rows if r["w"]["filled"])
    print(f"MODEL (mean of {A.seeds} seeds): fills {R[:, 0].mean():.1f} (sd {R[:, 0].std():.1f}), of them on live-filled windows {R[:, 3].mean():.1f}; "
          f"fill P&L {R[:, 1].mean():+.3f} (sd {R[:, 1].std():.3f}), model failed-try fees {R[:, 2].mean():.3f}; net {R[:, 1].mean() - R[:, 2].mean():+.3f}")
    print(f"LIVE: fills {live_f}, realized {live_p:+.3f} (failed-try fees are separate; see v5 notes)")
    print('model fills (all seeds) by live window (why, live filled):', dict(DIAG)); print('live windows:', dict(LW))
    for wy in ('whale_sold', 'expired', 'quiet', 'filled'):
        d = np.array([x[1] for x in DT if x[0] == wy]); e = np.array([x[2] for x in DT if x[0] == wy])
        if len(d): print(f'  {wy}: model fill ms before window end pctl 10/50/90 {np.percentile(d, [10, 50, 90]).round(0)}; ms after arm {np.percentile(e, [10, 50, 90]).round(0)}')
    pickle.dump(dict(res=res, live_f=live_f, live_p=live_p, n=len(rows)), open(f"{DATA}/v5.pkl", "wb"))

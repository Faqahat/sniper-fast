#!/usr/bin/env python3
"""SELLID step 1 (read-only): every bot-247 / bot-248 lot of haqq (code = CU price mod 1000, codes.pkl) on the multi-day tape
(exit/tape.npy = every mint haqq or our wallets traded, 10-22 03:07 -> 10-28 01:12 PKT), code-matched FIFO, mayhem excluded.

Per lot: buy row, cost, tokens, every sell of the same code that took tokens from it (row, tokens, SOL), first-sell row,
         realized curve P&L (SOL out - cost, pump fees in, tx costs NOT in), and the PATH of outside rows (haqq rows of every code
         removed, our two wallets kept = they are outside traders for him) for 300 slots after the buy:
         chain-clock ms after the buy, slot offset, idx, user id, buy flag, SOL, tokens; plus haqq's OTHER-code rows in that span.
Per sell of 247/248: the outside rows in the 0..3 slots before it (user, side, SOL, slot gap, idx gap, ms gap) and haqq other-code
         rows there (as pseudo-wallets 'HQ<code>').
Out: /home/moiz/sniper-data/haqq_dissect/sellid/s1.pkl"""
import pickle, sys, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
CODES = (247, 248)
HZ = 300


def main():
    t0 = time.time()
    R, MI, span, CC = X.tape()
    H = MI["who"]["haqq"]; OURS = (MI["who"]["FRA"], MI["who"]["AMS"])
    CO = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/pos/codes.pkl", "rb"))
    code = {k: v[0] for k, v in CO.items() if k[0] != "F"}
    hrow = np.flatnonzero(R["user"] == H)
    hk = [(int(s), int(i)) for s, i in zip(R["slot"][hrow], R["idx"][hrow])]
    hc = np.array([code.get(k, -1) for k in hk])
    mints = np.unique(R["mint"][hrow[np.isin(hc, CODES)]])
    print(f"haqq rows {len(hrow):,}, coded {np.mean(hc >= 0):.4f}; mints with 247/248 {len(mints):,} ({time.time() - t0:.0f}s)", flush=True)
    LOTS, SELLS = [], []
    nmay = 0
    for n_m, m in enumerate(mints.tolist()):
        info = MI["info"][m]
        if info.get("mayhem"): nmay += 1; continue
        M = X.Mint(m)
        isH = M.us == H
        cods = np.full(M.n, -1)
        for k in np.flatnonzero(isH).tolist(): cods[k] = code.get((int(M.sl[k]), int(M.ix[k])), -1)
        out_ = ~isH
        q = {c: [] for c in CODES}
        for k in np.flatnonzero(isH).tolist():
            c = int(cods[k])
            if c not in CODES: continue
            if M.bu[k]:
                fee = M.fee[k] if M.fee[k] > 0 else X.FEE
                hi = int(np.searchsorted(M.sl, M.sl[k] + HZ, side="right"))
                js = np.flatnonzero(out_[k + 1:hi]) + k + 1
                jh = np.flatnonzero(isH[k + 1:hi]) + k + 1
                lot = dict(id=len(LOTS), mint=m, code=c, k=k, slot=int(M.sl[k]), idx=int(M.ix[k]), cc=float(M.cc[k]), bt=int(M.bt[k]),
                           day=X.day_of(int(M.bt[k])), cost=float(M.so[k] * (1 + fee)), sin=float(M.so[k]), tok=float(M.tk[k]), fee=float(fee),
                           V0=float(M.vsp[k]), T0=float(M.vtp[k]), off_in_slot=float(M.cc[k] - M.sl[k] * X.SMS), age=(int(M.sl[k] - info["cs"]) if info.get("cs") is not None else None),
                           left=float(M.tk[k]), out=0.0, sells=[], first_sell_k=None, close_k=None,
                           p_dcc=(M.cc[js] - M.cc[k]).astype(np.float32), p_dsl=(M.sl[js] - M.sl[k]).astype(np.int16), p_ix=M.ix[js].astype(np.int32),
                           p_us=M.us[js].astype(np.int32), p_bu=M.bu[js].copy(), p_so=M.so[js].astype(np.float64), p_tk=M.tk[js].astype(np.float64),
                           p_k=js.astype(np.int32),
                           h_dcc=(M.cc[jh] - M.cc[k]).astype(np.float32), h_code=cods[jh].astype(np.int16), h_bu=M.bu[jh].copy(), h_so=M.so[jh].astype(np.float32),
                           h_k=jh.astype(np.int32))
                LOTS.append(lot); q[c].append(lot)
            else:
                need = float(M.tk[k]); tot = need; gross = float(M.so[k] * (1 - M.fee[k]))
                took = []
                while need > 0.5 and q[c]:
                    l = q[c][0]; t = min(l["left"], need)
                    l["out"] += gross * t / tot; l["left"] -= t; need -= t
                    l["sells"].append((k, t, gross * t / tot))
                    if l["first_sell_k"] is None: l["first_sell_k"] = k
                    took.append((l["id"], t / l["tok"]))
                    if l["left"] <= 0.5: l["close_k"] = k; q[c].pop(0)
                lo = int(np.searchsorted(M.sl, M.sl[k] - 3))
                w = np.arange(lo, k)
                wo = w[out_[w]]; wh = w[isH[w]]
                SELLS.append(dict(mint=m, code=c, k=k, slot=int(M.sl[k]), idx=int(M.ix[k]), cc=float(M.cc[k]), bt=int(M.bt[k]), day=X.day_of(int(M.bt[k])),
                                  tok=tot, sol=gross, lots=took, unmatched=need / tot,
                                  w_us=M.us[wo].astype(np.int32), w_bu=M.bu[wo].copy(), w_so=M.so[wo].astype(np.float32), w_ds=(M.sl[k] - M.sl[wo]).astype(np.int16),
                                  w_di=(M.ix[k] - M.ix[wo]).astype(np.int32), w_dcc=(M.cc[k] - M.cc[wo]).astype(np.float32), w_k=wo.astype(np.int32),
                                  w_rowgap=(k - wo).astype(np.int32),
                                  h_code=cods[wh].astype(np.int16), h_bu=M.bu[wh].copy(), h_ds=(M.sl[k] - M.sl[wh]).astype(np.int16), h_dcc=(M.cc[k] - M.cc[wh]).astype(np.float32)))
        # open at end: mark at the last price
        for c in CODES:
            for l in q[c]:
                l["mark"] = l["left"] * float(M.px[-1]) * 0.9875
        if n_m % 2000 == 0: print(f"  {n_m:,}/{len(mints):,} mints, lots {len(LOTS):,}, sells {len(SELLS):,} ({time.time() - t0:.0f}s)", flush=True)
    for l in LOTS:
        l["net"] = l["out"] + l.get("mark", 0.0) - l["cost"]
        if l["first_sell_k"] is not None:
            fs = l["first_sell_k"]
            # outside rows before the first sell (index into the path)
            l["n_before_sell"] = int(np.searchsorted(l["p_k"], fs))
            l["sell_dcc"] = float(X.tape()[3][X.tape()[2][l["mint"]][0] + fs] - l["cc"])
        else:
            l["n_before_sell"] = None; l["sell_dcc"] = None
    pickle.dump(dict(lots=LOTS, sells=SELLS, H=H, OURS=OURS), open(f"{OUT}/s1.pkl", "wb"))
    print(f"mayhem mints skipped {nmay}; lots {len(LOTS):,} sells {len(SELLS):,} ({time.time() - t0:.0f}s)")
    for c in CODES:
        v = [l for l in LOTS if l["code"] == c]
        print(f"code {c}: lots {len(v):,} net {sum(l['net'] for l in v):+.2f} SOL; sold {sum(l['first_sell_k'] is not None for l in v):,}")


if __name__ == "__main__":
    main()

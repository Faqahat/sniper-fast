#!/usr/bin/env python3
"""PRESEND FILTER, step 6: every chain-wide T2-like trigger (whale >= 6%, not in the create slot, as live arms) with the SAME arm
features as the live windows (feat.py) and a PROXY outcome (INFERRED) of a pre-send fill on it:
  fill-like = the first trade in the next 10 slots whose post-trade price is <= 0.88 x the price at the end of the previous slot;
  we buy right after it (live fills sit right after the dump in the token's trade order: 0 trades between, MEASURED on dev) at
  SIZE with pump's math; later trades applied as on chain (all fill); exit TP +10% / SL -20% on each later trade in slots <= fill + 1,
  else sell in slot fill + 2 after its trades at block index < 200 (~110 ms, the live median time-exit delay);
  net = sell after pump fees - SIZE - 0.00143 SOL (live per-fill tips + tx fees + rent not returned).
  labels also: y_nf = distinct other buyers in the fill slot (after it) and the next 2 slots; y_fb = follower-bot buyers among them.
Writes /home/moiz/sniper-data/presend_filter/chain_events.json"""
import sys, json, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import pmath as PM
from chainlib import Chain, B
import feat

SIZE = 340_000_000
COST = 1_430_000


def proxy(C, rows, q, size=SIZE):
    c = C.c
    S = c["s"][rows]; I = c["i"][rows]; BUY = c["buy"][rows]; SOL = c["sol"][rows]; TOK = c["tok"][rows]; VS = c["vsol"][rows]; VT = c["vtok"][rows]
    FB = c["fbps"][rows]; CB = c["cbps"][rows]
    v, t = int(VS[q]), int(VT[q]); fb, cb = int(FB[q]) or 95, int(CB[q]) or 30
    n = PM.net_of_budget(size, fb, cb)
    qt = t * (n - 1) // (v + n - 1)
    v += n; t -= qt
    s_in = int(S[q]); fr = (fb + cb) / 1e4
    why = "time"
    k = q + 1
    while k < len(rows):
        s = int(S[k])
        if s > s_in + 2 or (s == s_in + 2 and I[k] >= 200): break
        if BUY[k]:
            a = int(SOL[k]); dt = t * a // (v + a); v += a; t -= dt
        else:
            a = int(TOK[k]); o = v * a // (t + a); v -= o; t += a
        if s <= s_in + 1:
            val = (v * qt // (t + qt)) * (1 - fr) / size
            if val >= 1.10: why = "tp"; k += 1; break
            if val <= 0.80: why = "sl"; k += 1; break
        k += 1
    gross = v * qt // (t + qt)
    net = gross - PM.fees(gross, fb, cb) - size - COST
    return net, why


def main():
    t0 = time.time()
    C = Chain(); C.user_index()
    X = feat.Ctx(C)
    E = X.E
    out = []
    for e in range(len(E["tr_w"])):
        if E["tr_pct"][e] < 6.0 or E["tr_age"][e] < 1: continue
        mk = int(E["tr_m"][e]); mint = C.mints[mk]
        rows = C.morder[C.mstart[mk]:C.mstart[mk + 1]]
        s0, i0 = int(E["tr_s"][e]), int(E["tr_i"][e])
        S = C.c["s"][rows]; I = C.c["i"][rows]
        ks = np.nonzero((S == s0) & (I == i0))[0]
        if not len(ks): continue
        k = int(ks[0]); whale = int(E["tr_w"][e])
        row = dict(e=e, mint=mint, trig_slot=s0, bt=int(E["tr_bt"][e]), pct=float(E["tr_pct"][e]), vsol=float(E["tr_v"][e]), age=int(E["tr_age"][e]),
                   whale_sol=float(C.c["sol"][rows[k]]) / 1e9)
        feat.arm_feats(X, rows, k, whale, mint, s0, row)
        # fill-like + proxy outcome
        VS = C.c["vsol"][rows].astype(float); VT = C.c["vtok"][rows].astype(float); p = VS / np.maximum(VT, 1)
        q = None; ref = p[k]; last_slot = s0
        for j in range(k + 1, len(rows)):
            if S[j] > s0 + 10: break
            if S[j] != S[j - 1]: ref = p[j - 1]
            if p[j] <= 0.88 * ref and VS[j] < 100e9: q = j; break
        row["fill"] = q is not None
        if q is not None:
            net, why = proxy(C, rows, q)
            row["y_net"] = net / 1e9; row["y_why"] = why; row["fill_slot"] = int(S[q]); row["y_dump_is_whale"] = int(C.c["user"][rows[q]] == whale)
            U = C.c["user"][rows]; Bu = C.c["buy"][rows]
            bs = set(); j = q + 1
            while j < len(rows) and S[j] <= S[q] + 2:
                if Bu[j] and U[j] != U[q]: bs.add(int(U[j]))
                j += 1
            row["y_nf"] = len(bs); row["y_fb"] = len(bs & X.fbots)
            row["oc_depth"] = float(1 - p[q] / ref)
        out.append(row)
        if len(out) % 2000 == 0: print(len(out), f"{time.time() - t0:.0f}s", flush=True)
    json.dump(out, open(f"{B}/chain_events.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("events", len(out), "fill-like", sum(1 for r in out if r["fill"]), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

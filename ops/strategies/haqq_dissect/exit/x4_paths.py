#!/usr/bin/env python3
"""EXIT step 4 (read-only): per haqq lot, the path of outside trades after his buy (up to 300 slots = ~64 s) with
  * what he SAW: the lot's sell value / cost on the real tape after each outside trade (his own other trades included);
  * the exact REPLAY of the lot alone (his later trades removed; buys keep SOL, sells keep tokens), at full followers and with
    outside buy SOL x 0.9 (10% fewer followers).
Also his own exit (the sell that closed the lot; lots are closed by a matched sell, x2) as the number of outside rows before it.
Out: haqq_dissect/exit/paths.npz  (concatenated rows + per-lot offsets; lot order = haqq.pkl lots)"""
import pickle, time, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
HZ = 300


def main():
    t0 = time.time()
    R, MI, span, CC = X.tape()
    H = MI["who"]["haqq"]
    Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); LOTS = Z["lots"]
    by_m = {}
    for i, L in enumerate(LOTS): by_m.setdefault(L["mint"], []).append(i)
    off = np.zeros(len(LOTS) + 1, np.int64); parts = {k: [] for k in ("dcc", "dsl", "buy", "sol", "va", "vx", "vx9")}
    lot_exit = np.full(len(LOTS), -1, np.int64); lot_n = np.zeros(len(LOTS), np.int64)
    order = []
    pos = 0
    for n_m, (m, li) in enumerate(by_m.items()):
        M = X.Mint(m)
        o = M.us != H
        for i in li:
            L = LOTS[i]; k = L["k"]
            hi = int(np.searchsorted(M.sl, M.sl[k] + HZ, side="right"))
            js = np.flatnonzero(o[k + 1:hi]) + k + 1
            n = len(js); fee = M.fee[k] if M.fee[k] > 0 else X.FEE
            tok = L["tok"]; cost = L["cost"]
            va = X.sell_value(M.vs[js], M.vt[js], tok, fee) / cost
            v0 = M.vsp[k]; t0_ = M.vtp[k]; K = v0 * t0_
            out = []
            for fol in (1.0, 0.9):
                V = v0 + M.so[k]; T = K / V; tk = t0_ - T          # his buy at its real SOL in; tokens implied by the curve
                vv = np.empty(n)
                for a, j in enumerate(js.tolist()):
                    if M.bu[j]: V += M.so[j] * fol; T = K / V
                    else: T += M.tk[j]; V = K / T
                    vv[a] = (V - K / (T + tk)) * (1 - fee) / cost
                out.append(vv)
            parts["dcc"].append((M.cc[js] - M.cc[k]).astype(np.float32)); parts["dsl"].append((M.sl[js] - M.sl[k]).astype(np.int16))
            parts["buy"].append(M.bu[js]); parts["sol"].append(M.so[js].astype(np.float32))
            parts["va"].append(va.astype(np.float32)); parts["vx"].append(out[0].astype(np.float32)); parts["vx9"].append(out[1].astype(np.float32))
            if L["close_k"] is not None: lot_exit[i] = int(np.searchsorted(js, L["close_k"]))   # outside rows before his exit
            lot_n[i] = n
            order.append(i)
        if n_m % 3000 == 0: print(f"{n_m}/{len(by_m)} ({time.time() - t0:.0f}s)", flush=True)
    # re-order to lot index
    order = np.array(order); lens = np.array([len(x) for x in parts["dcc"]]); starts = np.concatenate([[0], np.cumsum(lens)])
    inv = np.empty(len(order), np.int64); inv[order] = np.arange(len(order))
    cat = {k: np.concatenate(v) for k, v in parts.items()}
    idx = np.concatenate([np.arange(starts[inv[i]], starts[inv[i] + 1]) for i in range(len(LOTS))])
    for k in cat: cat[k] = cat[k][idx]
    off[1:] = np.cumsum(lens[inv])
    np.savez(f"{X.OUT}/paths.npz", off=off, lot_exit=lot_exit, **cat)
    print(f"rows {off[-1]:,} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()

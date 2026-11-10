#!/usr/bin/env python3
"""H2 one wallet = several bots? Fingerprint census of every signed tx (ixn layout, CU limit, CU price, tips), decoded TradeEvent
amounts (quote in, fees), failed-tx error codes, and the SLIPPAGE boundary: for each buy attempt (landed or failed) the token
shortfall vs the curve state at its trigger (last outside trade <= 1 slot before).  Read-only.  -> h2_fp.json"""
import json, glob, collections, pickle
import numpy as np
import xlib as X, tlib9 as L, ev_dec
IN = "/home/it/sniper-data/botpnl9"
def toks_out(cbal, lam_in):            # tokens out for net SOL into the curve, constant product on virtual reserves
    vs = L.vsol(cbal); vt = cbal + L.V
    return vt - vs * vt / (vs + lam_in)
res = {}
for r in X.RUNS:
    own = L.own(r); t = X.load(r)
    evs = collections.Counter(); qin = collections.Counter(); per = collections.defaultdict(list)
    for fn in sorted(glob.glob(f"{IN}/{r}/p1_*.jsonl")):
        for l in open(fn, errors="replace"):
            if X.W not in l: continue
            d = json.loads(l)
            if (d.get("signers") or [None])[0] != X.W or d.get("err") is not None: continue
            for e in d.get("ev") or []:
                x = ev_dec.dec(e)
                if not x or x["user"] != X.W: continue
                evs[x["ix"]] += 1
                if x["is_buy"]: qin[x["sol"] + x["fee"] + x["cfee"]] += 1; per[d["bt"] // 3600].append(x["sol"] + x["fee"] + x["cfee"])
    # slippage: per buy attempt, state at its trigger vs state at its execution
    S, I, M = t.s, t.i, t.m
    rk = (M.astype(np.int64) << 40) | (S.astype(np.int64) - int(S.min())) << 12 | np.minimum(I, 4095)
    def state_before(m, s, i):          # index of the last tape row on mint m strictly before (s, i)
        k = (np.int64(m) << 40) | (np.int64(s - int(S.min())) << 12) | min(i, 4095)
        j = int(np.searchsorted(rk, k, "left")) - 1
        return j if j >= 0 and M[j] == m else -1
    rows = []
    for x in own:
        if x["kind"] not in ("buy", "fail") or not x["ixn"] or not any("Buy" in q for q in x["ixn"]): continue
        m = t.mint_ix.get(x["mint"])
        if m is None: continue
        j = state_before(m, x["s"], x["i"])
        if j < 0: continue
        # reference states: (a) end of slot s-1 (last row with slot < s), (b) the lowest-price state among outside rows in [s-1, exec)
        k = j
        while k >= t.mstart[m] and S[k] >= x["s"]: k -= 1
        if k < t.mstart[m]: continue
        lam = 691_358_023
        e_exec = toks_out(float(t.cpost[j]), lam); e_prev = toks_out(float(t.cpost[k]), lam)
        lo = k
        while lo - 1 >= t.mstart[m] and S[lo - 1] >= x["s"] - 1: lo -= 1
        e_best = toks_out(float(t.cpost[lo:j + 1].max()), lam)
        e_trig = e_prev
        err = None
        if x["kind"] == "fail":
            try: e = json.loads(x["err"]); c = e["InstructionError"][1]; err = c.get("Custom", c) if isinstance(c, dict) else c
            except Exception: err = str(x["err"])[:30]
        rows.append((x["kind"] == "buy", e_exec / e_trig - 1, err, e_exec / e_best - 1))
    ok = np.array([q[1] for q in rows if q[0]]); bad = [q for q in rows if not q[0]]
    errc = collections.Counter(str(q[2]) for q in bad)
    badv = np.array([q[1] for q in bad if str(q[2]) == errc.most_common(1)[0][0]]) if bad else np.array([])
    out = dict(events=dict(evs), buy_quote_in_lamports=qin.most_common(5),
               landed_shortfall_pct=np.percentile(ok, [0, 0.1, 0.5, 1, 5, 50, 95]).round(4).tolist(),
               landed_below=[float((ok < -q).mean()) for q in (0.05, 0.1, 0.15, 0.2, 0.25, 0.3)],
               fail_err_codes=errc.most_common(6),
               fail_main_code_shortfall_pct=np.percentile(badv, [0, 10, 25, 50, 75, 90, 100]).round(4).tolist() if len(badv) else None,
               n_landed=len(ok), n_fail_matched=len(bad))
    # where landed and failed overlap: shortfall bins
    edges = [-1, -0.4, -0.3, -0.25, -0.2, -0.15, -0.1, -0.05, 0, 1]
    hl = np.histogram(ok, edges)[0].tolist(); hf = np.histogram(badv, edges)[0].tolist() if len(badv) else []
    out["shortfall_bins"] = dict(edges=edges, landed=hl, failed_main=hf)
    okb = np.array([q[3] for q in rows if q[0]]); badb = np.array([q[3] for q in bad])
    out["vs_best_state_in_window"] = dict(landed=np.histogram(okb, edges)[0].tolist(), failed=np.histogram(badb, edges)[0].tolist())
    res[r] = out
    print(r, json.dumps(out), flush=True)
json.dump(res, open("h2_fp.json", "w"), indent=1)

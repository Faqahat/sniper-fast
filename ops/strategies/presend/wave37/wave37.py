#!/usr/bin/env python3
"""OMEN-3 step 1 [M on real fills]: the WAVE exit (decide at the first moment >= fill+150 ms with no outside buy in the last
150 ms, cap fill+1000 ms; TP10/SL20 checked meanwhile) vs our REAL exit, on every real pre-send fill (allruns/*.jsonl + haqqml fresh
tape). Both exits are re-simulated from our real landing position on the same curve walk (outside trades only, our own buy/sell
removed), so the comparison is paired and model-consistent. The wave sell lands after the SAME fill's measured decision->land delay
(real sell land - fill slot+2 boundary). Follower stress: each outside buy after our fill dropped w.p. cut (20 seeds).
Out: /home/it/sniper-data/omen3/wave_real.json (per fill) + summary on stdout."""
import json, glob, sys, numpy as np
TP = "/home/it/sniper-data/wave37/tab"; AR = "/home/it/sniper-data/wave37"
SMS = 212.5
T = np.load(TP + "/trades.npy", mmap_mode="r"); MI = {m: i for i, m in enumerate(json.load(open(TP + "/mints.json")))}
SL = np.load(TP + "/slots.npy", mmap_mode="r"); SLs = np.asarray(SL["slot"]); SLm = np.asarray(SL["maxi"])
mm = np.asarray(T["mint"]); order = np.argsort(mm, kind="stable"); ms_ = mm[order]
smax = int(T["slot"][-1])
def maxi(s):
    k = np.searchsorted(SLs, s); return int(SLm[k]) if k < len(SLs) and SLs[k] == s else 400
def cc(s, i): return s * SMS + i / max(maxi(s) + 1.0, i + 1.0) * SMS

def walk(t, cl, start, tok, V, Tk, f, t_end_fn, rng, cut, mode, c_in, ours, tp=1.10, sl=0.80):
    """from state (V,Tk) after our buy; returns value (lamports, after fee) of selling tok at the exit"""
    last_buy = c_in; t_dec = None; t_land = None; d_land = t_end_fn
    for k in range(start, len(t)):
        if k in ours: continue
        c = cl[k]
        if mode == "wave":
            g0 = min(max(c_in + 150.0, last_buy + 150.0), c_in + 1000.0)
            if t_dec is None and c > g0: t_dec = g0; t_land = g0 + d_land
            if t_land is not None and c >= t_land: break
        else:
            if c >= t_end_fn: break
        if t["buy"][k]:
            if cut > 0 and rng.random() < cut: continue
            sol = float(t["sol"][k]); dtk = Tk * sol / (V + sol); V += sol; Tk -= dtk
            if mode == "wave": last_buy = c
        else:
            tk_ = float(t["tok"][k]); so = V * tk_ / (Tk + tk_); V -= so; Tk += tk_
        if mode == "wave" and t_dec is None:
            val = (V - V * Tk / (Tk + tok)) * (1 - f)
            if val >= tp * SIZE[0] or val <= sl * SIZE[0]: t_dec = c; t_land = c + d_land
    return (V - V * Tk / (Tk + tok)) * (1 - f)
SIZE = [0]

rows = []
for fn in sorted(glob.glob(AR + "/*_r*.jsonl")):
    run = fn.split("/")[-1][:-6]
    C = {}; R = {}
    for l in open(fn):
        d = json.loads(l); e = d["ev"]
        if e == "presend_live_close": C[(d["mint"], d.get("pid"))] = d
        elif e == "presend_live_realized": R[(d["mint"], d.get("pid"))] = d
    for k, r in R.items():
        c = C.get(k)
        if not c or "sell_land" not in c or "land" not in c or c.get("sol_out_curve") is None: continue
        m = k[0]; s0, i0 = c["land"][0], c["land"][1]
        if m not in MI or s0 + 14 > smax: continue
        a, b = np.searchsorted(ms_, MI[m]), np.searchsorted(ms_, MI[m], side="right")
        idx = np.sort(order[a:b]); t = T[idx]
        sl = t["slot"].astype(np.int64); ii = t["idx"].astype(np.int64)
        pos = sl * 100000 + ii
        ex = c["sell_land"]; tok = float(c["tokens"]); sin = float(c["sol_in_curve"]); SIZE[0] = sin
        kb = np.searchsorted(pos, s0 * 100000 + i0)       # our buy row (or next)
        if kb >= len(t) or pos[kb] != s0 * 100000 + i0: continue
        ke = np.searchsorted(pos, ex[0] * 100000 + ex[1])
        ours = {kb}
        if ke < len(t) and pos[ke] == ex[0] * 100000 + ex[1]: ours.add(ke)
        V = float(t["vsol"][kb]); Tk = float(t["vtok"][kb])     # state after our buy
        f = (t["fee_bps"][0] + t["cfee_bps"][0]) / 1e4
        hi = min(len(t), kb + 4000)
        cl = np.array([cc(int(sl[q]), int(ii[q])) for q in range(hi)]) if hi else np.zeros(0)
        c_in = cl[kb]; c_ex = cc(ex[0], ex[1])
        dl = float(np.clip(c_ex - (s0 + 2) * SMS, 20, 400)) if c["exit_why"] in ("time-limit", "time-ms") else None
        sims = {}
        for cut in (0.0, 0.2):
            ns = 1 if cut == 0 else 20; rb = []; rw = []; rw2 = []
            for sd in range(ns):
                rng = np.random.default_rng([sd, kb]); rng2 = np.random.default_rng([sd, kb])
                rb.append(walk(t[:hi], cl, kb + 1, tok, V, Tk, f, c_ex, rng, cut, "time", c_in, ours))
                rw.append(walk(t[:hi], cl, kb + 1, tok, V, Tk, f, dl if dl is not None else 120.0, rng2, cut, "wave", c_in, ours))
                rng3 = np.random.default_rng([sd, kb])
                rw2.append(walk(t[:hi], cl, kb + 1, tok, V, Tk, f, dl if dl is not None else 120.0, rng3, cut, "wave", c_in, ours, 1.20, 0.50))
            sims[cut] = (np.mean(rb), np.mean(rw), np.mean(rw2))
        pre = [q for q in range(kb) if not t["buy"][q] and sl[q] >= s0 - 3]
        dump = max([float(t["sol"][q]) for q in pre], default=0) / 1e9
        rows.append(dict(dump=dump, bt=int(t["bt"][kb]), tpw=sims[0.0][2] / 1e9, tpw20=sims[0.2][2] / 1e9, run=run, m=m, pnl=r["pnl"] / 1e9, why=c["exit_why"], held=ex[0] - s0, sout=float(c["sol_out_curve"]) * (1 - f) / 1e9,
                         base=sims[0.0][0] / 1e9, wave=sims[0.0][1] / 1e9, base20=sims[0.2][0] / 1e9, wave20=sims[0.2][1] / 1e9, dl=dl, sin=sin / 1e9))
json.dump(rows, open("/home/it/sniper-data/wave37/wave37.json", "w"))
A = {k: np.array([r[k] for r in rows]) for k in ("base", "wave", "base20", "wave20", "sout", "pnl")}
n = len(rows); print("fills", n, "model err base vs real sout mSOL med/p90abs", np.median(A["base"] - A["sout"]) * 1e3, np.percentile(abs(A["base"] - A["sout"]), 90) * 1e3)
for lab, a, b in (("0%", "base", "wave"), ("-20%", "base20", "wave20")):
    d = (A[b] - A[a]) * 1e3; print(f"{lab}: wave - timer mSOL/fill mean {d.mean():+.3f} med {np.median(d):+.3f} better {np.mean(d>0)*100:.0f}% worse {np.mean(d<0)*100:.0f}%  sum {d.sum()/1e3:+.3f} SOL")
    bs = [np.random.default_rng(i).choice(d, n).mean() for i in range(2000)]; print("   bootstrap p5/p95", np.percentile(bs, [5, 95]).round(3))
for run in sorted({r["run"] for r in rows}):
    sel = [r for r in rows if r["run"] == run]; d = sum(r["wave"] - r["base"] for r in sel); d2 = sum(r["wave20"] - r["base20"] for r in sel)
    print(f"  {run}: n {len(sel)} delta {d:+.3f} (-20% {d2:+.3f}) SOL")

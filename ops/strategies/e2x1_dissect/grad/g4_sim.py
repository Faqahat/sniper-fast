#!/usr/bin/env python3
"""grad agent, step 4: the honest strategy universe — "buy near graduation, hold through it, sell N slots after migration".
Universe: every normal (non-mayhem, SOL-quoted) pump.fun token whose curve crosses V vSOL (first crossing; tokens that FAIL
to graduate included). Entry lands d_e after the crossing trade (live landing-delay sample, median scaled to 66 ms),
+5% price guard, pump fees in the curve maths; size S. Hold:
  - curve completes before a fallback fires -> sell on PumpSwap at migration + N slots (+ landing delay), pool maths + pool fees;
  - fallback while on the curve: stop-loss SL (mark-to-market value incl. fees/slippage <= (1-SL) x spent) or timeout TO.
  A fallback sell that lands after the curve completed fails -> held into the pool (GRAD exit).
Costs: 2.9 mSOL per filled round trip, 0.5 mSOL per reverted/failed buy (assumption).
Expected value over 10 stratified landing-delay samples (entry j, exit (3j+1) mod 10).
Out: /home/moiz/sniper-data/e2x1_dissect/grad/sim.pkl"""
import json, pickle, sys
import numpy as np
from glib import Tape, last_before, pool_state_after, pool_fee, pday, G

VS = [80, 85, 90, 95, 100, 105]
SIZES = [0.5, 1.0]
NS = [5, 10, 20, 48, 100, 200]
SLS = [0.10, 0.20, None]
TOS = [30, 120, 600, 1800]
RT_COST = 0.0029; FAIL_COST = 0.0005; GUARD = 1.05
SLOT_S = 0.21207

lc = json.load(open("/home/moiz/sniper-data/dipml/livecal.json"))
d = np.array(lc["deltas"], float); d = d * (66.0 / (np.median(d) * 212.07))         # live landing shape, median 66 ms
DLY = np.quantile(d, (np.arange(10) + 0.5) / 10)
PAIR = [(j, (3 * j + 1) % 10) for j in range(10)]

T = Tape()
import glob as _g
TAIL = [json.load(open(r))["tail_end_time"] for r in _g.glob("/home/moiz/sniper-data/collect/run_202610*_14*/run.json")]
TAIL = [t for t in TAIL if t < T.bt_of(T.shi)] + [T.bt_of(T.shi)]
EXITS = [(n, sl, to) for n in NS for sl in SLS for to in TOS]

def sim(m, V, S):
    rows = T.trades(m)
    if len(rows) == 0: return None
    vs = rows["vsol"]; above = np.nonzero(vs >= V * 1e9)[0]
    if len(above) == 0: return None
    k = int(above[0])
    if rows["buy"][k] == 0: return None
    K = float(rows["vsol"][k]) * float(rows["vtok"][k])
    f = (float(rows["fbps"][k]) + float(rows["cbps"][k])) / 1e4
    sk, ik = int(rows["slot"][k]), int(rows["idx"][k]); ck = T.clock(sk, ik)
    info = dict(mint=m, V=V, S=S, day=pday(rows["bt"][k]), bt=int(rows["bt"][k]), slot=sk, vk=float(vs[k]) / 1e9)
    comp = np.nonzero(rows["rtok"] == 0)[0]
    c = int(comp[0]) if len(comp) else None
    info["grad"] = c is not None
    info["edge"] = any(t - 2100 <= int(rows["bt"][k]) <= t for t in TAIL)     # life may run past a recording's end
    info["cross_completes"] = c == k
    w = (rows["slot"].astype(np.int64) >= sk - 47) & (np.arange(len(rows)) <= k)
    sg = np.where(rows["buy"][w] == 1, 1.0, -1.0)
    info["flow10"] = float((sg * rows["sol"][w]).sum()) / 1e9
    cr = T.cr.get(m); info["age_s"] = int(rows["bt"][k]) - cr["bt"] if cr else None
    mg = T.mig.get(m); info["has_mig"] = mg is not None
    if c is not None:
        info["t_complete_s"] = (int(rows["slot"][c]) - sk) * SLOT_S
        if mg: info["mig_minus_complete_slots"] = mg["slot"] - int(rows["slot"][c])
    if c == k:
        info["res"] = None; return info
    P = T.pool_events(mg["pool"]) if mg else None
    cm = T.clock(mg["slot"], mg["idx"]) if mg else None
    out = np.zeros(len(EXITS)); filled = 0.0; why = {}
    kinds = np.zeros(len(EXITS))    # share of samples that ended as GRAD exit
    for je, jx in PAIR:
        de, dx = DLY[je], DLY[jx]
        se, ie = T.position(ck + de)
        if (se, ie) <= (sk, ik): se, ie = sk, ik + 1
        e = max(last_before(rows, se, ie), k)
        if rows["rtok"][e] == 0:
            out -= FAIL_COST; why["late"] = why.get("late", 0) + 1; continue
        Ve, Te, Re = float(rows["vsol"][e]), float(rows["vtok"][e]), float(rows["rtok"][e])
        x = S * 1e9 / (1 + f); Vc = K / (Te - Re)
        if Ve + x >= Vc:
            xx = Vc - Ve; q = Re
        else:
            xx = x; q = Te - K / (Ve + x)
        spent = xx * (1 + f) / 1e9
        qd = float(rows["vtok"][k]) - K / (float(rows["vsol"][k]) + x)
        if (xx / q) > GUARD * (x / qd):
            out -= FAIL_COST; why["guard"] = why.get("guard", 0) + 1; continue
        filled += 1
        # mark-to-market path on the curve after our entry (our buy kept in the curve)
        end = c if c is not None else len(rows) - 1
        lim = int(np.searchsorted(rows["slot"], se + int(1800 / SLOT_S) + 50, "right")) - 1   # nothing after the longest timeout matters
        end = min(end, max(lim, e))
        idx = np.arange(e + 1, end + 1) if end > e else np.arange(0)
        V2 = rows["vsol"][idx].astype(float) + xx
        val = (V2 - K / (K / V2 + q)) * (1 - f) / 1e9
        if len(idx):
            sl_ = rows["slot"][idx].astype(np.int64); nn = np.maximum(T.N[np.clip(sl_ - T.slo, 0, len(T.N) - 1)], 1)
            clk = sl_ + np.minimum(rows["idx"][idx] / nn, 0.999999)
        else: clk = np.zeros(0)
        ce = T.clock(se, ie)
        def curve_exit(dec_clock):
            """sell decided at dec_clock, lands dx later: (value or None if the curve completed first)"""
            sx, ix = T.position(dec_clock + dx)
            t = last_before(rows, sx, ix)
            if c is not None and t >= c: return None
            t = max(t, e)
            V2 = float(rows["vsol"][t]) + xx
            return (V2 - K / (K / V2 + q)) * (1 - f) / 1e9
        grad_val = {}
        if c is not None and mg is not None:
            for n in NS:
                sx, ix = T.position(cm + n + dx)
                kk = last_before(P, sx, ix)
                pb, pq = pool_state_after(P, kk, mg)
                fee = pool_fee(P, kk)
                grad_val[n] = (pq - pb * pq / (pb + q)) * (1 - fee) / 1e9
        for xi, (n, sl, to) in enumerate(EXITS):
            dec = ce + to / SLOT_S
            if sl is not None and len(val):
                hit = np.nonzero(val <= (1 - sl) * spent)[0]
                if len(hit): dec = min(dec, clk[hit[0]])
            v = None
            if c is None or dec < T.clock(int(rows["slot"][c]), int(rows["idx"][c])):
                v = curve_exit(dec)
            if v is None:
                if c is None: v = val[-1] if len(val) else spent * 0      # tape end (no completion): last state
                elif mg is None: v = np.nan                                 # completed, migration not recorded
                else: v = grad_val[n]; kinds[xi] += 1
            out[xi] += v - spent - RT_COST
    info["res"] = out / len(PAIR); info["fill"] = filled / len(PAIR); info["why"] = why; info["gradexit"] = kinds / len(PAIR)
    return info

if __name__ == "__main__":
    cand = []
    for m, v in T.M["mx"].items():
        cr = T.cr.get(m)
        if v < 80e9 or cr is None or cr.get("mayhem"): continue
        mg = T.mig.get(m)
        if mg and not mg["quote"].startswith("So111"): continue
        cand.append(m)
    print("candidates", len(cand), flush=True)
    R = []
    for n_, m in enumerate(cand):
        for V in VS:
            for S in SIZES:
                r = sim(m, V, S)
                if r is not None: R.append(r)
        if n_ % 500 == 0: print(n_, len(R), flush=True)
    pickle.dump(dict(R=R, EXITS=EXITS, DLY=DLY.tolist()), open(G + "/sim.pkl", "wb"))
    print("saved", len(R))

#!/usr/bin/env python3
"""hybrid step 2: replay the copy-exit hybrid on every live pre-send fill (and the 24 h shadow row-c fills).
Rule: if E2x1 / Grozoe holds the token when our fill lands (or buys while we still hold), skip our normal exit and sell
L ms after we SEE their first sell (L = our landing distribution, 21 quantiles, median 66 ms), with fallbacks
max hold H s and optional stop-loss -20 % (both also land L ms after the decision).
Live pricing (like ops/dip/exit200/check.py): after our real sell, our tokens are put back into the pool
(vsol += our sell SOL, vtok -= our tokens); hybrid proceeds = real proceeds * model(exit state) / model(real-sell state);
hybrid P&L = real P&L + (hybrid proceeds - real proceeds) (sell fee/tx cost unchanged).
Shadow pricing: our buy is inserted into the tape at the shadow fill (vsol += s_c, vtok -= T for every later trade);
baseline = sell decided 200 ms after the fill; P&L = v*(1-1.25%) - sol_in*(1+1.25%) - 2.9 mSOL.
Out: sniper-data/e2x1_dissect/hybrid/sim.pkl"""
import json, pickle, bisect, collections, numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/hybrid"; TP = "/home/moiz/sniper-data/haqqml/fresh/tape"
E = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"; G = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
B = pickle.load(open(f"{OUT}/build.pkl", "rb")); C = B["tape"]; TEND = B["tape_end_slot"]
S = np.load(f"{TP}/slots.npy", mmap_mode="r"); s_lo = int(S["slot"][0])
NB = np.full(TEND - s_lo + 2, 1000.0); NB[np.asarray(S["slot"]).astype(np.int64) - s_lo] = np.asarray(S["maxi"]) + 1.0
SLOT_MS = (int(S["bt"][-1]) - int(S["bt"][0])) * 1000.0 / (int(S["slot"][-1]) - int(S["slot"][0]))
clk = lambda s, i: s + min(i / NB[s - s_lo], 0.999999)
dq = json.load(open("/home/moiz/sniper-data/e2x1_dissect/ourspeed/delay_q.json"))
Q = np.array(dq["q_fra"]) * 66.0 / dq["med_fra"]          # landing delay, median 66 ms
FR = 0.0125; TRIP = 0.0029; GRAD_VTOK = 280.0e12
# lots.pkl (recon, RPC-completed) for E2x1 events where it covers the time
LOTS = pickle.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/lots.pkl", "rb"))
LOT_LO = min(l["bt"] for l in LOTS)
lot_ev = collections.defaultdict(list)
for l in LOTS:
    lot_ev[l["mint"]].append((l["s"], l["i"], 1, l["tok"]))
    for sg, s, i, bt, tk, sol in l["sells"]:
        if s: lot_ev[l["mint"]].append((s, i, 0, tk))
# per-mint tape
o = np.argsort(C["mint"], kind="stable"); mm = C["mint"][o]
edges = np.flatnonzero(np.r_[True, mm[1:] != mm[:-1], True])
TAPE = {}
for a, b in zip(edges[:-1], edges[1:]):
    ix = o[a:b]
    rows = sorted(zip(C["slot"][ix].tolist(), C["idx"][ix].tolist(), C["j"][ix].tolist(), C["user"][ix].tolist(), C["buy"][ix].tolist(),
                      C["sol"][ix].tolist(), C["tok"][ix].tolist(), C["vsol"][ix].tolist(), C["vtok"][ix].tolist()))
    TAPE[mm[a]] = rows
VARS = [(w, ent, H, sl) for w in ("E2x1", "Grozoe", "either") for ent in ("in", "in+after") for H in (30, 60, 120, 1800) for sl in (True, False)]
WS = {"E2x1": {E}, "Grozoe": {G}, "either": {E, G}}

LOT_HI = 1793199900   # recon tables end 10-28 20:05 PKT
def wallet_events(mint, W, rows, ft):
    if W == E and LOT_LO + 3600 <= ft <= LOT_HI - 1800:
        return sorted(lot_ev.get(mint, [])), "lots"
    return [(r[0], r[1], r[4], r[6]) for r in rows if r[3] == W], "tape"

def sim(pos, rows, fill_key, our_keys, addback, T, cost, base_land_clk, ent_cut_key, entry_state, fill_clock):
    """returns {variant: (value_at_exit, flag, hold_s, why)} plus holder info."""
    after = [r for r in rows if (r[0], r[1], r[2]) > fill_key and (r[0], r[1]) not in our_keys]
    def st(r):
        vs, vt = r[7], r[8]
        if addback and (r[0], r[1]) > addback[0]: vs, vt = vs + addback[1], vt - T
        return vs, vt
    vals = []; clks = []
    for r in after:
        vs, vt = st(r); vals.append(vs * T / (vt + T)); clks.append(clk(r[0], r[1]))
    v_entry = entry_state[0] * T / (entry_state[1] + T)
    grad_clk = next((clk(r[0], r[1]) for r in after if r[8] <= GRAD_VTOK), None)
    end_clk = clk(TEND, 10**6)
    def value_at(dec):
        flag = ""
        if grad_clk is not None and dec > grad_clk: flag = "grad"
        if dec > end_clk: flag = flag or "tape_end"
        out = []
        for L in Q:
            k = bisect.bisect_left(clks, dec + L / SLOT_MS) - 1
            out.append(vals[k] if k >= 0 else v_entry)
        return float(np.mean(out)), flag
    # holders
    info = {}
    for W in (E, G):
        ev, src = wallet_events(pos["mint"], W, rows, pos["ft"])
        tev = [(r[0], r[1], r[4], r[6]) for r in rows if r[3] == W]
        t_holds = (lambda n, b: b > 0 and n > 0.01 * b)(sum(t if b else -t for s, i, b, t in tev if (s, i) < fill_key[:2]), sum(t for s, i, b, t in tev if b and (s, i) < fill_key[:2]))
        net = sum(t if b else -t for s, i, b, t in ev if (s, i) < fill_key[:2]); bought = sum(t for s, i, b, t in ev if b and (s, i) < fill_key[:2])
        holds = bought > 0 and net > 0.01 * bought
        nb = [(s, i) for s, i, b, t in ev if b and (s, i) > fill_key[:2]]
        first_after = nb[0] if nb else None
        enter_while = (not holds) and first_after is not None and clk(*first_after) <= ent_cut_key
        start = fill_key[:2] if holds else (first_after if enter_while else None)
        sell = next(((s, i) for s, i, b, t in ev if not b and start and (s, i) > start), None)
        info[W] = dict(holds=holds, tape_holds=t_holds, enter_while=enter_while, first_after=first_after, sell=sell, src=src,
                       sold_before=bought > 0 and not holds, last_buy=max([(s, i) for s, i, b, t in ev if b and (s, i) < fill_key[:2]], default=None))
    res = {}
    for v in VARS:
        w, ent, H, sl = v
        trig = [W for W in WS[w] if info[W]["holds"] or (ent == "in+after" and info[W]["enter_while"])]
        if not trig: continue
        cand = [(fill_clock + H * 1000.0 / SLOT_MS, "max")]
        sells = [info[W]["sell"] for W in trig if info[W]["sell"]]
        if sells: cand.append((clk(*min(sells)), "copy"))
        if sl:
            k = next((k for k, x in enumerate(vals) if x <= 0.8 * cost), None)
            if k is not None: cand.append((clks[k], "sl"))
        dec, why = min(cand)
        val, flag = value_at(dec)
        res[v] = (val, flag, (dec - fill_clock) * SLOT_MS / 1000.0, why)
    return res, info, value_at

LIVE = []
for f in B["fills"]:
    rows = TAPE.get(f["mint"])
    if not rows or f["real"] is None or f["result"] != "sold": continue
    ss, si = f["sells"][0][0], f["sells"][0][1]
    mine = [r for r in rows if (r[0], r[1]) == (ss, si)]
    buy = [r for r in rows if (r[0], r[1]) == (f["fs"], f["fi"])]
    if not mine or not buy or len(f["sells"]) > 1: LIVE.append(dict(f, skip="our tx not on tape" if (not mine or not buy) else "multi-sell")); continue
    pre = [r for r in rows if (r[0], r[1]) < (ss, si)]
    v_ref = pre[-1][7] * f["tokens"] / (pre[-1][8] + f["tokens"])
    fill_key = (f["fs"], f["fi"], 99); T = f["tokens"]
    res, info, value_at = sim(f, rows, fill_key, {(ss, si), (f["fs"], f["fi"])}, ((ss, si), mine[0][5]), T, f["sol_in"], None,
                              clk(ss, si) - 132.0 / SLOT_MS, (buy[0][7], buy[0][8]), clk(f["fs"], f["fi"]))
    hyb = {v: f["real"] + (f["sold"] * r[0] / v_ref - f["sold"]) / 1e9 for v, r in res.items()}
    LIVE.append(dict(f, res=res, hyb=hyb, info=info, v_ref=v_ref))
SH = []
for f in B["shadow"]:
    rows = TAPE.get(f["mint"])
    if not rows: SH.append(dict(f, skip="no tape")); continue
    T = f["tokens"]; vs0, vt0 = f["vs0"], f["vt0"]; s_c = vs0 * T / (vt0 - T)
    fill_key = (f["fs"], f["fi"], f["fj"]); fc = clk(f["fs"], f["fi"]) + 1e-6
    ent_cut = fc + (200.0 - 66.0) / SLOT_MS      # their buy seen before our 200 ms sell decision
    # every later row carries our buy: emulate with addback at the fill itself
    res, info, value_at = sim(f, rows, fill_key, set(), ((f["fs"], f["fi"] - 1 if f["fi"] else -1), s_c), T, f["sol_in"], None, ent_cut,
                              (vs0 + s_c, vt0 - T), fc)
    vb, flb = value_at(fc + 200.0 / SLOT_MS)
    pnl = lambda v: v * (1 - FR) / 1e9 - f["sol_in"] * (1 + FR) / 1e9 - TRIP
    SH.append(dict(f, res=res, info=info, base=pnl(vb), base_flag=flb, hyb={v: pnl(r[0]) for v, r in res.items()}))
pickle.dump(dict(live=LIVE, shadow=SH, VARS=VARS, SLOT_MS=SLOT_MS, Q=Q.tolist()), open(f"{OUT}/sim.pkl", "wb"))
print("live", len(LIVE), "skipped", collections.Counter(x.get("skip") for x in LIVE), "affected(either,in+after)", sum(1 for x in LIVE if x.get("res") and ("either", "in+after", 1800, False) in x["res"]))
print("shadow", len(SH), "affected", sum(1 for x in SH if x.get("res") and ("either", "in+after", 1800, False) in x["res"]), "SLOT_MS", SLOT_MS)

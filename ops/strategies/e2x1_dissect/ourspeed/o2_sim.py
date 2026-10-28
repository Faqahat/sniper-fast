#!/usr/bin/env python3
"""ourspeed step 2: what E2x1's trades would make for US at our landing speed (read-only, offline).

A ORACLE-PICKS : his lots, his trigger trade T (trig_*; OLD lots: the last other-wallet trade before his buy), same SOL size,
                 our buy lands d after T (d = our measured live delay shape, 21 quantiles, rescaled to median L),
                 guard +5% over the post-T price, counterfactual tape WITHOUT E2x1 + Grozoe (sibling) trades.
                 exits: 'his' = our entry + his own hold (block clock), '200ms' = entry + 200 ms + sell delay d',
                        'band' = entry + 18 / 34 / 83 s (FRESH / MINUTE / OLD).
B COPY-TRADE   : real tape (he and every follower stay in), our buy lands d after HIS buy, guard +5% over the post-his-buy
                 price; 'copy' exit = his first sell + d'; also '200ms' and 'band' exits from our entry.
Curve maths = /home/moiz/sniper-haqqml/sim.py (constant product, our SOL kept in the curve until we sell, fee f on in/out).
Followers phi: remove phi x other wallets' buy SOL landing between our entry and min(exit, entry + 10 slots) ("fast followers");
               'full' variant removes phi x buy SOL over the whole hold (harsh for long holds).
Output: per-lot expected values (npz) for every (mode, exit, L, phi) -> o3_tables.py builds the report tables.
"""
import pickle, json, sys, collections
import numpy as np

R = "/home/moiz/sniper-data/e2x1_dissect/recon"
O = "/home/moiz/sniper-data/e2x1_dissect/ourspeed"
ME = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
SIB = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
SLOT_MS = 212.07
K0 = 30e9 * 1.073e15
BAND_H = {"FRESH": 18.0, "MINUTE": 34.0, "OLD": 83.0}
LS = [10, 20, 35, 50, 66, 90, 120, 150, 200]
PHIS = [0.0, 0.2, 0.4]
FOLLOW_SLOTS = 10

# ---- block clock ------------------------------------------------------------------------------------------------
B = np.load(f"{O}/blocks.npy"); s_lo = int(B["slot"][0]); NB = np.zeros(int(B["slot"][-1]) - s_lo + 2, np.int64)
NB[B["slot"].astype(np.int64) - s_lo] = B["maxi"].astype(np.int64) + 1
def bsize(s):
    k = np.clip(np.asarray(s, np.int64) - s_lo, 0, len(NB) - 1); return NB[k]
def clock(s, i):
    n = bsize(s).astype(float); n[n <= 0] = 1
    return np.asarray(s, float) + np.minimum(np.asarray(i, float) / n, 0.999999)
def position(t):
    t = np.asarray(t, float); s = np.floor(t).astype(np.int64); fr = t - s; n = bsize(s)
    for _ in range(12):
        miss = n <= 0
        if not miss.any(): break
        s = np.where(miss, s + 1, s); fr = np.where(miss, 0.0, fr); n = bsize(s)
    return s, np.floor(fr * np.maximum(n, 1)).astype(np.int64)

dq = json.load(open(f"{O}/delay_q.json")); Q = np.array(dq["q_pre"]); QMED = dq["med_pre"]

# ---- tape ------------------------------------------------------------------------------------------------------
Z = pickle.load(open(f"{R}/tape.pkl", "rb"))
L = [l for l in pickle.load(open(f"{R}/lots.pkl", "rb")) if l["day"] in ("D0", "D1")]
need = {l["mint"] for l in L}

def key(s, i, j=0):
    return (np.asarray(s, np.int64) << 24) | (np.asarray(i, np.int64) << 4) | np.asarray(j, np.int64)

class M:  # one mint, one tape variant
    pass

def build(mint, cf):
    tr = [t for t in Z["trades"][mint] if t[16]]
    tr.sort(key=lambda t: (t[0], t[1], t[2]))
    s = np.array([t[0] for t in tr], np.int64); i = np.array([t[1] for t in tr], np.int64); j = np.array([t[2] for t in tr], np.int64)
    buy = np.array([t[6] for t in tr], bool); sol = np.array([t[7] for t in tr], float)
    v = np.array([t[9] for t in tr], float); vt = np.array([t[10] for t in tr], float)
    w = np.array([t[4] in (ME, SIB) for t in tr], bool)
    sig = [t[15] for t in tr]
    if cf:
        net = np.where(w, np.where(buy, sol, -sol), 0.0); cum = np.cumsum(net)
        Kr = v * vt; v = v - cum; vt = Kr / v
        keep = ~w
        s, i, j, buy, sol, v, vt = s[keep], i[keep], j[keep], buy[keep], sol[keep], v[keep], vt[keep]
        sig = [g for g, k in zip(sig, keep) if k]; w = w[keep]
    m = M(); m.s, m.i, m.j, m.buy, m.sol, m.v, m.vt, m.w = s, i, j, buy, sol, v, vt, w
    m.sig = sig; m.k = key(s, i, j); m.sigpos = {g: q for q, g in enumerate(sig)}
    ob = np.where(buy & ~w, sol, 0.0); m.cb = np.concatenate([[0.0], np.cumsum(ob)])  # cb[q+1] = other buy SOL up to row q
    return m

def before(m, s, i):
    """index of last row strictly before chain position (s, i); -1 if none"""
    return np.searchsorted(m.k, key(s, i), "left") - 1

def trip(m, k_anchor, t_entry, x, f, q_ref_fn, exits, phi_list, swap_px, G=1.05):
    """vectorised over draws. t_entry: clock array; exits: dict name -> clock array (same length).
    returns dict (exit, phi, fullflag) -> (fill bool array, pnl_pre array SOL)"""
    se, ie = position(t_entry)
    ke = before(m, se, ie); ke = np.maximum(ke, k_anchor)
    Ve = m.v[ke]; Te = m.vt[ke]; K = Ve * Te
    q = Te - K / (Ve + x)
    qref = q_ref_fn(x)
    fill = q >= qref / G
    out = {}
    last_k = len(m.s) - 1
    for nm, tx in exits.items():
        tx = np.maximum(tx, t_entry)
        sx, ix = position(tx)
        kx = before(m, sx, ix); kx = np.maximum(kx, ke)
        Vx = m.v[kx]
        # buys between entry and exit by others (cf tape: no E2x1/sib rows; real tape: w rows excluded from cb)
        kf = before(m, *position(np.minimum(tx, t_entry + FOLLOW_SLOTS))); kf = np.maximum(np.minimum(kf, kx), ke)
        bf = m.cb[kf + 1] - m.cb[ke + 1]; ball = m.cb[kx + 1] - m.cb[ke + 1]
        past = kx >= last_k
        for phi in phi_list:
            for full in ((False, True) if phi > 0 else (False,)):
                V2 = Vx + x - phi * (ball if full else bf)
                V2 = np.maximum(V2, 1e6)
                o = (V2 - K / (K / V2 + q)) * (1 - f)
                if swap_px is not None:  # graduated and our exit is after the curve's last trade: his realized price per token
                    o = np.where(past, q * swap_px, o)
                out[(nm, phi, full)] = (fill, np.where(fill, o / 1e9 - x * (1 + f) / 1e9, 0.0))
    return out

def run():
    cache_cf = {}; cache_rl = {}
    rows = []
    LL = L[:int(sys.argv[1])] if len(sys.argv) > 1 else L
    for n, l in enumerate(LL):
        mint = l["mint"]
        if mint not in Z["trades"]: continue
        if mint not in cache_cf: cache_cf[mint] = build(mint, True); cache_rl[mint] = build(mint, False)
        mc, mr = cache_cf[mint], cache_rl[mint]
        f = (l["fbps"] + l["cbps"]) / 1e4
        S = l["cost"]; x = S * 1e9 / (1 + f)
        # his buy / sell positions (real tape)
        hb_t = float(clock(np.array([l["s"]]), np.array([l["i"]]))[0])
        if l["sells"]:
            sg, ss, si = l["sells"][0][0], l["sells"][0][1], l["sells"][0][2]
            hs_t = float(clock(np.array([ss]), np.array([si]))[0])
        else:
            hs_t = None
        tok_tot = sum(z[4] for z in l["sells"]) or l["tok"]
        swap_px = (l["proceeds"] * 1e9 / tok_tot) if (l["swap_sell"] and tok_tot) else None
        # trigger
        trig = None; tsrc = "trig"
        if l.get("trig_sig") and l["trig_sig"] in mc.sigpos: trig = mc.sigpos[l["trig_sig"]]
        else:
            tsrc = "prev"; kb = before(mc, l["s"], l["i"]); trig = int(kb) if kb >= 0 else None
        res = {"lot_id": l["lot_id"], "day": l["day"], "bot": l["bot"], "mint": mint, "S": S, "his_pnl": l["pnl"], "tsrc": tsrc,
               "his_hold_slots": (hs_t - hb_t) if hs_t else np.nan}
        # ---- V: validation = his own position on the cf tape (entry at his buy, exit at his sell) vs his real proceeds ----
        if hs_t:
            te = np.array([hb_t]); kb = int(before(mc, l["s"], l["i"]))
            o = trip(mc, kb, te, x, f, lambda x: 0.0, {"his": np.array([hs_t])}, [0.0], swap_px, G=1e9)
            res["V"] = float(o[("his", 0.0, False)][1][0]); res["V_real"] = l["proceeds"] - l["cost"]
        for L_ms in LS:
            d = Q * (L_ms / QMED) / SLOT_MS; d2 = d[::-1]
            # ---- A: oracle picks (cf tape); A2: same picks on the REAL tape (he and his sibling still trade) ----
            for MODE, mm in (("A", mc), ("A2", mr)):
                kt = trig if MODE == "A" else (mr.sigpos.get(mc.sig[trig]) if trig is not None else None)
                if kt is None: continue
                tT = float(clock(np.array([mm.s[kt]]), np.array([mm.i[kt]]))[0])
                te = tT + d
                se, ie = position(te); same = (se == mm.s[kt]) & (ie <= mm.i[kt]); te = np.where(same, mm.s[kt] + (mm.i[kt] + 1) / max(int(bsize(np.array([mm.s[kt]]))[0]), 1), te)
                Vd, Td = mm.v[kt], mm.vt[kt]
                qref = lambda x, Vd=Vd, Td=Td: Td - Vd * Td / (Vd + x)
                ex = {"band": te + BAND_H[l["bot"]] * 1000 / SLOT_MS, "200ms": te + (200 + d2 * SLOT_MS) / SLOT_MS}
                if hs_t: ex["his"] = te + (hs_t - hb_t)
                o = trip(mm, kt, te, x, f, qref, ex, PHIS if MODE == "A" else [0.0, 0.2], swap_px)
                for (nm, phi, full), (fl, p) in o.items():
                    res[f"{MODE}|{nm}|{L_ms}|{phi}|{'full' if full else 'fast'}"] = (fl.mean(), p.mean())
            # ---- B: copy trade (real tape) ----
            kh = mr.sigpos.get(l["buy_sig"])
            if kh is not None and hs_t:
                te = hb_t + d
                se, ie = position(te); same = (se == l["s"]) & (ie <= l["i"]); te = np.where(same, l["s"] + (l["i"] + 1) / max(int(bsize(np.array([l["s"]]))[0]), 1), te)
                Vd, Td = mr.v[kh], mr.vt[kh]
                qref = lambda x, Vd=Vd, Td=Td: Td - Vd * Td / (Vd + x)
                ex = {"copy": np.maximum(hs_t + d2, te), "band": te + BAND_H[l["bot"]] * 1000 / SLOT_MS, "200ms": te + (200 + d2 * SLOT_MS) / SLOT_MS}
                o = trip(mr, kh, te, x, f, qref, ex, PHIS, swap_px)
                for (nm, phi, full), (fl, p) in o.items():
                    res[f"B|{nm}|{L_ms}|{phi}|{'full' if full else 'fast'}"] = (fl.mean(), p.mean())
        rows.append(res)
        if n % 300 == 0: print(n, len(L), flush=True)
    pickle.dump(rows, open(f"{O}/sim_rows.pkl", "wb"))
    print("rows", len(rows))

if __name__ == "__main__":
    run()

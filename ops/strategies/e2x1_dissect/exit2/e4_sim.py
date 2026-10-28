#!/usr/bin/env python3
"""exit2 step 4: simulated P&L of the TEST-day trips under different EXITS (curve maths as ourspeed/o2_sim.py and haqqml/sim.py).
Entry modes:
  H  = his entry (real tape, his tokens, his cost). Exit at clock t: curve state after the last trade with clock <= t; if his real
       sell already happened by t its SOL is added back to the curve (x8 convention). Validation: exit at his real sell = his proceeds.
  O  = our entry: counterfactual tape WITHOUT E2x1 + Grozoe, our buy (his SOL size) lands d after the trigger trade T (= last outside
       trade before his buy), d = our live delay shape (ourspeed delay_q, 21 quantiles) rescaled to median 66 ms, guard +5 % over the
       post-T price; fast-follower haircut phi (other buys in the 10 slots after our entry removed x phi).
Exits (clock): HIS = his real first sell (+ d' for O); COPY (O only) = his sell + d'; 200ms; FIXED band 18/34/83 s (FRESH/MINUTE/OLD);
  RULE = first event with GBDT p >= thr, + d'; RULE_SIB = RULE or sibling's sell, + d'; TREE = single-tree high-lift leaves, + d';
  1800 s timeout when nothing fires. Out: e4.txt, e4_rows.pkl"""
import sys, json, pickle, collections
import numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/exit2"; OS = "/home/moiz/sniper-data/e2x1_dissect/ourspeed"
SLOT_MS = 212.0; LMED = float(sys.argv[1]) if len(sys.argv) > 1 else 66.0
TEST0 = 1793113200 - 79 * 60; TEST1 = TEST0 + 86400
BAND = {0: 18.0, 1: 34.0, 2: 83.0}; TIMEOUT = 1800.0
dq = json.load(open(f"{OS}/delay_q.json")); Q = np.array(dq["q_pre"]); D = Q * (LMED / dq["med_pre"]) / SLOT_MS; D2 = D[::-1]
Z = np.load(f"{OUT}/tape_his.npz"); wid = int(Z["wid"]); sid = int(Z["sid"])
slot = Z["slot"].astype(np.int64); idx = Z["idx"].astype(np.int64); mint = Z["mint"]; user = Z["user"]; buy = Z["buy"].astype(bool)
sol = Z["sol"].astype(np.float64); tok = Z["tok"].astype(np.float64); vsol = Z["vsol"].astype(np.float64); vtok = Z["vtok"].astype(np.float64)
fee = (Z["fee_bps"].astype(np.float64) + Z["cfee_bps"].astype(np.float64)) / 1e4; bt = Z["bt"].astype(np.int64)
um, st = np.unique(mint, return_index=True); en = np.append(st[1:], len(mint)); span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
S = np.load("/home/moiz/sniper-data/haqqml/fresh/tape/slots.npy"); s_lo = int(S["slot"].min())
NB = np.zeros(int(S["slot"].max()) - s_lo + 2, np.int64); NB[S["slot"].astype(np.int64) - s_lo] = S["maxi"].astype(np.int64) + 1
def bsize(s):
    k = np.clip(np.asarray(s, np.int64) - s_lo, 0, len(NB) - 1); return NB[k]
def clock(s, i):
    n = bsize(s).astype(float); n[n <= 0] = 400
    return np.asarray(s, float) + np.minimum(np.asarray(i, float) / n, 0.999999)
def position(t):
    t = np.asarray(t, float); s = np.floor(t).astype(np.int64); fr = t - s; n = bsize(s)
    for _ in range(12):
        miss = n <= 0
        if not miss.any(): break
        s = np.where(miss, s + 1, s); fr = np.where(miss, 0.0, fr); n = bsize(s)
    return s, np.floor(fr * np.maximum(n, 1)).astype(np.int64)
def key(s, i, j=0): return (np.asarray(s, np.int64) << 24) | (np.asarray(i, np.int64) << 4) | np.asarray(j, np.int64)
class M: pass
def build(m, cf):
    a, b = span[m]; r = np.arange(a, b)
    w = (user[r] == wid) | (user[r] == sid)
    s, i, bb, so, v, vt = slot[r], idx[r], buy[r], sol[r], vsol[r].copy(), vtok[r].copy()
    if cf:
        net = np.where(w, np.where(bb, so, -so), 0.0); cum = np.cumsum(net); Kr = v * vt; v = v - cum; vt = Kr / v
        keep = ~w; r, s, i, bb, so, v, vt, w = r[keep], s[keep], i[keep], bb[keep], so[keep], v[keep], vt[keep], w[keep]
    x = M(); x.r, x.s, x.i, x.buy, x.sol, x.v, x.vt, x.w = r, s, i, bb, so, v, vt, w
    x.k = key(s, i, Z["j"][r]); x.cb = np.concatenate([[0.0], np.cumsum(np.where(bb & ~w, so, 0.0))]); x.rowpos = {int(q): n for n, q in enumerate(r)}
    return x
def before(m, s, i): return np.searchsorted(m.k, key(s, i), "left") - 1
def trip_pnl(m, k_anchor, t_entry, x, f, qref_fn, exits, phi, addback=None, G=1.05):
    se, ie = position(t_entry); ke = np.maximum(before(m, se, ie), k_anchor)
    Ve, Te = m.v[ke], m.vt[ke]; K = Ve * Te; q = Te - K / (Ve + x); fill = q >= qref_fn(x) / G
    out = {}
    for nm, tx in exits.items():
        tx = np.maximum(tx, t_entry); sx, ix = position(tx); kx = np.maximum(before(m, sx, ix), ke); Vx = m.v[kx].copy()
        if addback is not None:  # (his sell row position, his gross sell SOL): add back if his sell is at/before our exit
            Vx = Vx + np.where(kx >= addback[0], addback[1], 0.0)
        kf = np.maximum(np.minimum(before(m, *position(np.minimum(tx, t_entry + 10))), kx), ke)
        bf = m.cb[kf + 1] - m.cb[ke + 1]
        V2 = np.maximum(Vx + x - phi * bf, 1e6); o = (V2 - K / (K / V2 + q)) * (1 - f)
        out[nm] = (fill, np.where(fill, o / 1e9 - x * (1 + f) / 1e9, 0.0))
    return out
TR = pickle.load(open(f"{OUT}/trips.pkl", "rb")); E = np.load(f"{OUT}/e3_scores.npz"); EV = np.load(f"{OUT}/ev.npz"); META = EV["meta"]; p = E["p"]; THR = float(E["thr"])
FEATS = list(EV["feats"]); FI = {f: k for k, f in enumerate(FEATS)}; Xf = EV["X"]
leaf = E["leaf"]; good_leaf = set(int(l) for l in (json.load(open(f"{OUT}/e4_leaves.json")) if __import__("os").path.exists(f"{OUT}/e4_leaves.json") else []))
# first fire per trip (event row -> tape row)
def first_fire(mask):
    ff = {}
    for k in np.flatnonzero(mask):
        t = int(META[k, 0])
        if t not in ff: ff[t] = int(META[k, 4])
    return ff
FIRE = {"RULE": first_fire(p >= THR), "RULE_SIB": first_fire((p >= THR) | (Xf[:, FI["sib_sold_2"]] > 0)), "SIB": first_fire(Xf[:, FI["sib_sold_2"]] > 0),
        "FIRSTSELL": first_fire((Xf[:, FI["ev_buy"]] == 0)), "SIBSELL": first_fire((Xf[:, FI["ev_sib"]] > 0) & (Xf[:, FI["ev_buy"]] == 0)),
        "TOP3SELL": first_fire((Xf[:, FI["ev_buy"]] == 0) & (Xf[:, FI["ev_rank"]] <= 2) & (Xf[:, FI["ev_sol_rel"]] >= 0.01)), "TREE": first_fire(np.isin(leaf, list(good_leaf))) if good_leaf else {}}
for qq in (0.95, 0.98, 0.995):
    FIRE[f"RULE@q{qq}"] = first_fire(p >= np.quantile(p[E["val"]], qq))
rows = []
for ti, t in enumerate(TR):
    if not (TEST0 <= t["bt"] < TEST1) or t["close"] is None: continue
    m = t["mint"]; mr = build(m, False); mc = build(m, True); f = float(fee[t["entry"]])
    S_sol = t["cost"] * 1e9; x = S_sol / (1 + f)   # lamports into curve (trip cost is SOL)
    ke_h = t["entry"]; ks_h = t["sells"][0]
    hb_t = float(clock(np.array([slot[ke_h]]), np.array([idx[ke_h]]))[0]); hs_t = float(clock(np.array([slot[ks_h]]), np.array([idx[ks_h]]))[0])
    gross_his = sol[ks_h]  # SOL his sell took out of the curve (gross, lamports)
    res = dict(trip=ti, mint=m, bot=t["bot"], S=S_sol / 1e9, hold_slots=hs_t - hb_t)
    ex_t = {}
    for nm, ff in FIRE.items():
        ex_t[nm] = float(clock(np.array([slot[ff[ti]]]), np.array([idx[ff[ti]]]))[0]) if ti in ff else None
    # ---- H: his entry, real tape ----
    kb = mr.rowpos[ke_h]; ks = mr.rowpos[ks_h]
    te = np.array([hb_t]); one = np.ones(1)
    ex = {"HIS": np.array([hs_t]) - 1e-6, "200ms": te + (200 / SLOT_MS), "FIXED": te + BAND[t["bot"]] * 1000 / SLOT_MS, "TIMEOUT": te + TIMEOUT * 1000 / SLOT_MS}
    o = trip_pnl(mr, kb, te, x, f, lambda x: 0.0, ex, 0.0, addback=(ks, gross_his), G=1e9)
    for nm, (fl, pv) in o.items(): res[f"H|{nm}"] = float(pv[0])
    res["H|real"] = (sum(sol[k] * (1 - fee[k]) for k in t["sells"]) - S_sol) / 1e9
    # rule exits with sell delay d'
    for nm, tt in ex_t.items():
        tx = (tt + D2) if tt is not None else (hb_t + TIMEOUT * 1000 / SLOT_MS + 0 * D2)
        o = trip_pnl(mr, kb, np.full(len(D2), hb_t), x, f, lambda x: 0.0, {nm: tx}, 0.0, addback=(ks, gross_his), G=1e9)
        res[f"H|{nm}"] = float(o[nm][1].mean()); res[f"H|{nm}|fired"] = tt is not None
        txb = np.minimum(tx, hb_t + BAND[t["bot"]] * 1000 / SLOT_MS + D2); tx6 = np.minimum(tx, hb_t + 60000 / SLOT_MS + D2)
        o = trip_pnl(mr, kb, np.full(len(D2), hb_t), x, f, lambda x: 0.0, {"b": txb, "6": tx6}, 0.0, addback=(ks, gross_his), G=1e9)
        res[f"H|{nm}|FIXED"] = float(o["b"][1].mean()); res[f"H|{nm}|60s"] = float(o["6"][1].mean())
    # ---- O: our entry on the cf tape ----
    pre = [q for q in range(span[m][0], ke_h) if user[q] != wid and user[q] != sid]
    if pre:
        kt = mc.rowpos[pre[-1]]; tT = float(clock(np.array([mc.s[kt]]), np.array([mc.i[kt]]))[0]); te = tT + D
        se, ie = position(te); same = (se == mc.s[kt]) & (ie <= mc.i[kt]); te = np.where(same, mc.s[kt] + (mc.i[kt] + 1) / max(int(bsize(np.array([mc.s[kt]]))[0]), 1), te)
        Vd, Td = mc.v[kt], mc.vt[kt]; qref = lambda x, Vd=Vd, Td=Td: Td - Vd * Td / (Vd + x)
        ex = {"HIS": hs_t + D2, "200ms": te + (200 / SLOT_MS) + D2, "FIXED": te + BAND[t["bot"]] * 1000 / SLOT_MS + D2, "TIMEOUT": te + TIMEOUT * 1000 / SLOT_MS}
        for nm, tt in ex_t.items():
            ex[nm] = (tt + D2) if tt is not None else ex["TIMEOUT"]; ex[nm + "|FIXED"] = np.minimum(ex[nm], ex["FIXED"]); ex[nm + "|60s"] = np.minimum(ex[nm], te + 60000 / SLOT_MS + D2)
        for phi in (0.0, 0.2):
            o = trip_pnl(mc, kt, te, x, f, qref, ex, phi)
            for nm, (fl, pv) in o.items(): res[f"O{phi}|{nm}"] = float(pv.mean()); res[f"O{phi}|{nm}|fill"] = float(fl.mean())
    rows.append(res)
pickle.dump(rows, open(f"{OUT}/e4_rows_{int(LMED)}.pkl", "wb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
P(f"TEST trips simulated {len(rows)} (closed, 10-27 18:41 -> 10-28 18:41 PKT); our landing median {LMED:.0f} ms; SOL pre tx-costs")
bots = np.array([r["bot"] for r in rows])
def tot(k, mask=None):
    a = np.array([r.get(k, np.nan) for r in rows]); a = a[mask] if mask is not None else a; return np.nansum(a)
P(f"validation H|HIS (sim at his real sell) vs H|real (tape proceeds): {tot('H|HIS'):+.3f} vs {tot('H|real'):+.3f}")
for mode in ("H", "O0.0", "O0.2"):
    P(f"\n== entry {mode} ==   {'exit':12} {'ALL':>9} {'FRESH':>9} {'MINUTE':>9} {'OLD':>9}   gap-recovery")
    base = {b: tot(f"{mode}|FIXED", bots == b) for b in (0, 1, 2)}; base["all"] = tot(f"{mode}|FIXED"); his = {b: tot(f"{mode}|HIS", bots == b) for b in (0, 1, 2)}; his["all"] = tot(f"{mode}|HIS")
    for nm in ["HIS", "200ms", "FIXED", "TIMEOUT"] + [n + sfx for n in FIRE for sfx in ("", "|FIXED", "|60s")]:
        k = f"{mode}|{nm}"
        if not any(k in r for r in rows): continue
        a = tot(k); bb = [tot(k, bots == b) for b in (0, 1, 2)]
        rec = (a - base["all"]) / (his["all"] - base["all"]) if his["all"] != base["all"] else float("nan")
        P(f"  {nm:18} {a:+9.3f} {bb[0]:+9.3f} {bb[1]:+9.3f} {bb[2]:+9.3f}   {100*rec:6.1f}%" + (f"   fill {np.nanmean([r.get(k+'|fill', np.nan) for r in rows]):.2f}" if mode != "H" else "") + (f"   fired {100*np.mean([r.get(k+'|fired', False) for r in rows]):.0f}%" if mode == "H" and nm in FIRE else ""))
open(f"{OUT}/e4_{int(LMED)}.txt", "w").write("\n".join(out) + "\n")

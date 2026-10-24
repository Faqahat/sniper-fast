#!/usr/bin/env python3
# COPY-TRADE REPLAY (read-only, offline): copy ONLY the wallet's FIRST buy on each token.
# Our buy lands after every trade whose block position is within T ms after their buy (block ms = slot*212 + index/slot_size*212),
# T = 0 (reference: right behind them), 35, 75, 150, 300 ms. Our buy of B SOL is inserted into the curve and everything after it is
# replayed exactly (buyers' SOL in, sellers' tokens in), so our price impact counts. Costs: pump fee (fbps+cbps of the trade before
# us) on both sides + 0.0015 SOL per tx (0.0005 priority + 0.001 tip) for the buy and for the sell.
# Every exit also lands T ms after its trigger. Variants: "all" = keep every follower; "drop2" = conservative, every outside buy
# landing within 2 slots after our fill is removed (followers whose slippage limit we broke); "slip" = only follower buys whose
# decoded slippage limit fails at the replayed price are removed (when decoded; unknown = kept).
# Graduation: if the replayed curve completes (115 SOL / real tokens gone) we sell at that last curve price (flag grad). Tape end: sell at the last price (flag end).
# output: out/copy_rows.pkl.gz (per position x T x B x variant: pnl per rule) + rule names
import os, sys, json, gzip, pickle, bisect, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feat, lib3
from multiprocessing import Pool
TX = 0.0015
TS = [0, 35, 75, 150, 300]; BS = [0.25, 0.5, 1.0, 2.0]
VARS = ["all", "drop2", "slip"]
GRADV = 115e9; GRADT = 279_950_000_000_000      # measured: completed curves end at vsol 115.005 SOL / vtok 279.9e12 (110 SOL was too low)
def msf(t):
    n = lib3.slot_size(t["s"]) or 450
    return t["s"] * 212.0 + min(t["i"] / max(n, t["i"] + 1), 0.999) * 212.0
def fr(t): return (t["fbps"] + t["cbps"]) / 1e4
# ------------------------------------------------------------------ rules
RULES = []   # (name, kind, params)
RULES.append(("mirror_first", "mir", 0)); RULES.append(("mirror_last", "mir", 1))
for tl in (20, 40, 60, 120, 300, 600): RULES.append((f"time{tl}", "time", tl))
for tp in (0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75, 1.00):
    for sl in (0.05, 0.10, 0.15, 0.20, 0.30, None):
        for tl in (20, 40, 60, 120, 300, 600):
            RULES.append((f"tp{int(tp*100)}_sl{int(sl*100) if sl else 'X'}_t{tl}", "tpsl", (tp, sl, tl)))
for tp in (0.10, 0.20, 0.30, 0.50, None):
    for sl in (0.10, 0.20, None):
        RULES.append((f"mirF_tp{int(tp*100) if tp else 'X'}_sl{int(sl*100) if sl else 'X'}", "mirtpsl", (tp, sl)))
for arm in (0.10, 0.20, 0.30):
    for drop in (0.05, 0.10, 0.20):
        for tl in (60, 300):
            RULES.append((f"trail{int(arm*100)}_{int(drop*100)}_t{tl}", "trail", (arm, drop, tl, 0.20)))
for idle in (2, 5, 10, 20):
    for tl in (60, 300):
        RULES.append((f"idle{idle}s_t{tl}", "idle", (idle, tl)))
for x in (0.5, 1.0, 2.0, 4.0):
    for tl in (30, 120):
        RULES.append((f"folsol{x}_t{tl}", "folsol", (x, tl)))
for x in (0.3, 1.0):
    for tl in (60, 300):
        RULES.append((f"osell{x}_t{tl}", "osell", (x, tl)))
NAMES = [r[0] for r in RULES]
SLIP = {}
def load_slip():
    for p in ("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl", os.path.join(lib3.HERE, "raw/slip3.jsonl")):
        if not os.path.exists(p): continue
        for l in open(p):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("kind") in ("sol", "tok"): SLIP[r["sig"]] = (r["kind"], r["a1"], r["a2"])
T_, L, P = None, None, None
def init():
    global T_, L, P
    T_, _ = lib3.load_tapes(); L = lib3.load_launches(); P = json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))); load_slip()
def replay(tr, k0, W, T, B, var, c):
    """returns dict(arrays) of the replayed path after our fill, or None"""
    m0 = msf(tr[k0]); n = len(tr)
    idx = k0 + 1
    while idx < n and msf(tr[idx]) - m0 <= T: idx += 1
    ahead = [t for t in tr[k0 + 1:idx] if t["user"] != W]
    prev = tr[idx - 1]
    V, Tk = prev["vsol"], prev["vtok"]
    if V >= GRADV or not Tk: return None
    f = fr(prev); X = int(B * 1e9 / (1 + f)); q = Tk * X // (V + X); V += X; Tk -= q
    p_in = X / q if q else 0
    fill_slot = prev["s"]; fill_ms = max(msf(prev), m0 + T)
    kept = []; slipped = 0; dropped = 0
    # replayed path: state after each kept trade
    msA = [fill_ms]; vA = [(V * q / (Tk + q)) * (1 - f) / 1e9 / B]; sA = [fill_slot]; outbuyA = [0.0]; osellA = [0.0]; lastbuyA = [fill_ms]
    wsA = []  # W's sells: ms
    grad = False; cum_ob = 0.0; lastb = fill_ms
    first_ws_all = next((msf(t) for t in tr[k0 + 1:] if t["user"] == W and not t["buy"]), None)
    last_ws_all = next((msf(t) for t in reversed(tr[k0 + 1:]) if t["user"] == W and not t["buy"]), None)
    stop_ms = max(fill_ms + 900_000, (last_ws_all or 0) + T + 5000)
    for k in range(idx, n):
        t = tr[k]; mt = msf(t)
        if t["user"] == W and not t["buy"]: wsA.append(mt)
        if var == "drop2" and t["buy"] and t["user"] != W and t["s"] - fill_slot <= 2: dropped += 1; continue
        if t["buy"]:
            lim = SLIP.get(t["sig"]) if var == "slip" else None
            if lim is not None and lim[0] == "sol" and Tk * t["sol"] // (V + t["sol"]) < lim[2]: slipped += 1; continue
            if lim is not None and lim[0] == "tok" and (lim[1] >= Tk or (V * lim[1] // (Tk - lim[1]) + 1) * (1 + fr(t)) > lim[2]): slipped += 1; continue
            if lim is not None and lim[0] == "tok":
                cst = V * lim[1] // (Tk - lim[1]) + 1; V += cst; Tk -= lim[1]
            else:
                d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d
            if t["user"] != W: cum_ob += t["sol"] / 1e9; lastb = mt
            osell_sz = 0.0
        else:
            so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
            osell_sz = t["sol"] / 1e9 if t["user"] != W else 0.0
        msA.append(mt); sA.append(t["s"]); outbuyA.append(cum_ob); osellA.append(osell_sz); lastbuyA.append(lastb)
        vA.append((V * q / (Tk + q)) * (1 - fr(t)) / 1e9 / B if Tk > 0 else 0)
        if V >= GRADV or Tk <= GRADT: grad = True; break
        if mt > stop_ms: break   # 15 min after our fill and past W's last sell
    return dict(ms=np.array(msA), v=np.array(vA), ob=np.array(outbuyA), osell=np.array(osellA), lastb=np.array(lastbuyA), grad=grad, fill_ms=fill_ms,
                n_ahead=len(ahead), n_ahead_buy=sum(1 for t in ahead if t["buy"]), ahead_buy_sol=sum(t["sol"] for t in ahead if t["buy"]) / 1e9,
                ahead_users=len({t["user"] for t in ahead if t["buy"]}), entry_vs_them=(prev["vsol"] / prev["vtok"]) / (tr[k0]["vsol"] / tr[k0]["vtok"]),
                fws=first_ws_all, lws=last_ws_all, slipped=slipped, dropped=dropped)
def exit_at(R, ms_target):
    """index of the state we sell at: after the last trade with ms <= ms_target (never before our fill)"""
    j = bisect.bisect_right(R["ms"], ms_target) - 1
    return max(0, min(j, len(R["ms"]) - 1))
def first_true(mask, j0, j1):
    if j1 < j0: return None
    w = np.nonzero(mask[j0:j1 + 1])[0]
    return j0 + int(w[0]) if len(w) else None
def eval_rules(R, T, B):
    ms = R["ms"]; v = R["v"]; f = R["fill_ms"]; n = len(ms); out = []; flags = []
    def res(j, why=""):
        pnl = v[j] * B - B - 2 * TX
        fl = "grad" if (R["grad"] and j == n - 1) else ("end" if j == n - 1 else "")
        return round(float(pnl), 6), fl
    def tcap(tl): return exit_at(R, f + tl * 1000)
    for name, kind, prm in RULES:
        if kind == "mir":
            tgt = R["fws"] if prm == 0 else R["lws"]
            j = exit_at(R, tgt + T) if tgt is not None else n - 1
        elif kind == "time": j = tcap(prm)
        elif kind == "tpsl":
            tp, sl, tl = prm; jc = tcap(tl)
            mask = (v >= 1 + tp + 2 * TX / B) | ((v <= 1 - sl) if sl else False)
            jt = first_true(mask, 1, jc)
            j = exit_at(R, ms[jt] + T) if jt is not None else jc
        elif kind == "mirtpsl":
            tp, sl = prm; tgt = R["fws"]; jm = exit_at(R, tgt + T) if tgt is not None else tcap(600)
            mask = np.zeros(n, bool)
            if tp: mask |= v >= 1 + tp + 2 * TX / B
            if sl: mask |= v <= 1 - sl
            jt = first_true(mask, 1, jm) if (tp or sl) else None
            j = min(jm, exit_at(R, ms[jt] + T)) if jt is not None else jm
        elif kind == "trail":
            arm, drop, tl, sl = prm; jc = tcap(tl); pk = np.maximum.accumulate(v)
            mask = ((pk >= 1 + arm) & (v <= pk * (1 - drop))) | (v <= 1 - sl)
            jt = first_true(mask, 1, jc); j = exit_at(R, ms[jt] + T) if jt is not None else jc
        elif kind == "idle":
            idle, tl = prm; jc = tcap(tl)
            # first state where the next trade comes > idle s after the last outside buy (or the path ends)
            lb = R["lastb"]; nxt = np.append(ms[1:], 1e18)
            jt = first_true((nxt - lb) > idle * 1000, 0, jc)
            j = exit_at(R, max(lb[jt] + idle * 1000, ms[jt]) + T) if jt is not None else jc
        elif kind == "folsol":
            x, tl = prm; jc = tcap(tl)
            jt = first_true(R["ob"] >= x * B, 1, jc); j = exit_at(R, ms[jt] + T) if jt is not None else jc
        elif kind == "osell":
            x, tl = prm; jc = tcap(tl)
            jt = first_true(R["osell"] >= x, 1, jc); j = exit_at(R, ms[jt] + T) if jt is not None else jc
        p, fl = res(j); out.append(p); flags.append(fl)
    return out, flags
def work(pi):
    p = P[pi]
    if p.get("nobuy") or p["mayhem"]: return []
    tr = T_[p["m"]]; W = lib3.W3[p["w"]]; c = L[p["m"]]
    k0 = p["k0"]; rows = []
    for T in TS:
        for var in VARS:
            if T == 0 and var != "all": continue
            for B in BS:
                R = replay(tr, k0, W, T, B, var, c)
                if R is None: continue
                pn, fl = eval_rules(R, T, B)
                rows.append(dict(pi=pi, w=p["w"], m=p["m"], run=p["run"], bt=p["bt"], T=T, B=B, var=var, pnl=pn,
                                 grad_rules=[i for i, x in enumerate(fl) if x == "grad"], end_rules=[i for i, x in enumerate(fl) if x == "end"],
                                 n_ahead=R["n_ahead"], n_ahead_buy=R["n_ahead_buy"], ahead_users=R["ahead_users"], ahead_buy_sol=R["ahead_buy_sol"],
                                 entry_vs_them=R["entry_vs_them"], slipped=R["slipped"], dropped=R["dropped"]))
    return rows
if __name__ == "__main__":
    init()
    out = []
    with Pool(8, initializer=init) as pool:
        for r in pool.imap_unordered(work, range(len(P)), chunksize=4): out += r
    pickle.dump(dict(names=NAMES, rows=out), gzip.open(os.path.join(lib3.HERE, "out/copy_rows.pkl.gz"), "wb"))
    print("rows", len(out), "rules", len(NAMES))

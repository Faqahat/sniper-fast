#!/usr/bin/env python3
# RULE COMPILER + REPLAY (read-only). Compiles the JSON DSL rules (p3_llm.py prompt) and replays each on the day arrays
# (p1_build.py): R2 = train, R3 = test, R1 = lockbox (only for the final shortlist).
#  - trigger: vectorized mask on causal features at the trigger trade (event buy/sell/any) or at an idle moment ("idle":
#    the token had no trade for idle_slots; window features of windows <= idle_slots are zero, quiet = idle_slots).
#  - landing: race -> trigger arrival + 35 / 50 ms; non-race -> next slot start + 35 ms; idle -> idle moment + 35 ms.
#    arrival(tx) = slot*212 + index/blocksize*212 ms (blocksize from core/slotsize.json, else 400). Trades arriving before
#    us are ahead. Guard: price at landing > 1.05 x price right after the trigger -> failed buy (-0.0005 SOL).
#  - be_trigger: WE are the trigger buyer (real trigger buys by others stand in for ours; that wallet's later trades are
#    removed; size = the trigger's size).
#  - path: every later trade of the token replayed on our curve; follower buys whose slippage limit our buy breaks are
#    dropped (empirical slack model of sel/selexit2.py, per signature); sells applied as tokens in.
#  - exit: tp / sl (price multiple vs our fill), max_slots timer, exit events (dev_sell, big_sell, big_buy, fam_sell,
#    bot_buy:<id>, bot_sell:<id>); fills at the end of the decision slot; graduation -> pre-graduation state.
#  - costs: pump fee (event bps) both sides + 0.0035 SOL per round trip; failed buy 0.0005.
#  - ONE OPEN POSITION AT A TIME per rule (greedy in landing order across all tokens) + an unconstrained sample.
import sys, os, json, math, re, collections
import numpy as np
PO = "/home/moiz/sniper-data/strategies/patterns"
SMS = 212.0; FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9
WTC = {"creator": 1, "insider": 2, "new": 3, "fresh": 3, "bot": 4, "other": 0, "w": 0, **{f"F{k}": 10 + k for k in range(1, 11)}}
EXIT_EV = re.compile(r"^(dev_sell|big_sell|big_buy|fam_sell|bot_buy:\d+|bot_sell:\d+)$")
DAYS = {}

def load_day(run):
    z = np.load(f"{PO}/day_{run}.npz"); M = json.load(open(f"{PO}/day_{run}_meta.json"))
    d = {k: z[k] for k in z.files}
    d["M"] = M; d["FI"] = {k: i for i, k in enumerate(M["feats"])}
    nt = len(M["meta"]); cnt = np.bincount(d["tok"], minlength=nt)
    off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    d["tend"] = (off + cnt)[d["tok"]]
    nxt = np.empty(len(d["s"]), np.int64); nxt[:-1] = d["s"][1:]; nxt[-1] = 10 ** 12
    last = np.zeros(len(d["s"]), bool); last[(off + cnt - 1)[cnt > 0]] = True
    nxt[last] = 10 ** 12
    d["gap_next"] = nxt - d["s"]                      # slots until the token's next trade (huge if none)
    d["last_slot"] = int(d["s"].max())
    F = d["F"]; FI = d["FI"]
    d["dipbot"] = (d["buy"] == 0) & (d["sol"] >= 1.08e9) & (F[:, FI["move"]] <= -4.65) & (F[:, FI["age"]] <= 1623)
    d["f7"] = (d["buy"] == 1) & (d["sol"] >= 0.9e9) & (d["sol"] <= 3e9) & (F[:, FI["quiet"]] >= 20) & (F[:, FI["age"]] >= 150) & (F[:, FI["curve"]] - d["sol"] / 1e9 <= 45)
    return d

# ------------------------------------------------------------------ compile
def compile_rule(r, feats, themes, xl):
    """-> normalized rule dict or raises ValueError"""
    ev = str(r.get("event", "any")).lower()
    if ev not in ("buy", "sell", "any", "idle"): raise ValueError(f"event {ev}")
    idle = int(r.get("idle_slots") or 20) if ev == "idle" else 0
    idle = max(3, min(idle, 3000)) if ev == "idle" else 0
    mode = str(r.get("mode", "follow")).lower()
    if mode != "be_trigger" or ev != "buy": mode = "follow"
    race = bool(r.get("race", True)) if ev != "idle" and mode == "follow" else False
    size = float(r.get("size") or 0.5); size = max(0.35, min(size, 0.75))
    ex = r.get("exit") or {}
    tp = ex.get("tp"); sl = ex.get("sl")
    tp = float(tp) if isinstance(tp, (int, float)) and tp > 1.0 else None
    sl = float(sl) if isinstance(sl, (int, float)) and 0 < sl < 1.0 else None
    ms = int(ex.get("max_slots") or 30); ms = max(1, min(ms, 3000))
    on = sorted({str(x) for x in (ex.get("on") or []) if EXIT_EV.match(str(x))})
    conds = []; special = []
    for c in r.get("when") or []:
        if not isinstance(c, (list, tuple)) or len(c) != 3: raise ValueError(f"cond {c}")
        f, op, v = c
        if op not in (">=", "<=", ">", "<", "==", "!=", "in", "not_in"): raise ValueError(f"op {op}")
        f = str(f)
        if f.startswith("holds:") or f.startswith("acted:"):
            parts = f.split(":")
            if f.startswith("holds:") and len(parts) == 2 and parts[1].lstrip("B").isdigit(): special.append(("holds", int(parts[1].lstrip("B")), 0, op, float(v)))
            elif f.startswith("acted:") and len(parts) == 3 and parts[1].lstrip("B").isdigit() and parts[2].isdigit(): special.append(("acted", int(parts[1].lstrip("B")), int(parts[2]), op, float(v)))
            else: raise ValueError(f"special {f}")
            continue
        if f == "wt":
            vals = v if isinstance(v, list) else [v]
            codes = []
            for x in vals:
                x = str(x)
                if x in ("fam", "family"): codes += list(range(11, 21))
                elif x in WTC: codes.append(WTC[x])
                else: raise ValueError(f"wt {x}")
            if op in ("==", "in"): conds.append((f, "in", codes))
            elif op in ("!=", "not_in"): conds.append((f, "not_in", codes))
            else: raise ValueError("wt op")
            continue
        if f in ("theme", "x"):
            ref = themes if f == "theme" else xl
            vals = v if isinstance(v, list) else [v]
            codes = [ref.index(str(x)) for x in vals if str(x) in ref]
            if not codes: raise ValueError(f"{f} {v}")
            conds.append((f, "in" if op in ("==", "in") else "not_in", codes)); continue
        if f == "bid" and isinstance(v, str): v = v.lstrip("B")
        if f not in feats: raise ValueError(f"feature {f}")
        if op in ("in", "not_in"):
            vals = v if isinstance(v, list) else [v]
            conds.append((f, op, [float(x) for x in vals]))
        else: conds.append((f, op, float(v)))
    if ev in ("buy", "sell"): conds.append(("ev_buy", "==", 1.0 if ev == "buy" else 0.0))
    R = dict(name=str(r.get("name", ""))[:80], event=ev, idle=idle, mode=mode, race=race, size=size, tp=tp, sl=sl, max_slots=ms, on=on,
             conds=conds, special=special, why=str(r.get("why", ""))[:200], src=r.get("src"))
    R["sig"] = signature(R)
    return R

def rnd2(x):
    if isinstance(x, list): return [rnd2(y) for y in x]
    if x == 0: return 0
    return float(f"{x:.2g}")

def signature(R):
    c = sorted((f, op, rnd2(v) if not isinstance(v, list) else sorted(rnd2(v))) for f, op, v in R["conds"])
    return json.dumps([R["event"], R["idle"], R["mode"], R["race"], c, sorted(R["special"]), rnd2(R["tp"] or 0), rnd2(R["sl"] or 0), rnd2(R["max_slots"]), R["on"]])

# ------------------------------------------------------------------ trigger mask
def opmask(x, op, v):
    if op == ">=": return x >= v
    if op == "<=": return x <= v
    if op == ">": return x > v
    if op == "<": return x < v
    if op == "==": return x == v
    if op == "!=": return x != v
    if op == "in": return np.isin(x, v)
    if op == "not_in": return ~np.isin(x, v)

IDLE_ZERO = lambda w, idle: w <= idle
def triggers(d, R):
    F = d["F"]; FI = d["FI"]
    if R["event"] == "idle":
        cand = np.flatnonzero((d["gap_next"] >= R["idle"]) & (d["s"] + R["idle"] <= d["last_slot"]))
        X = F[cand].copy()
        X[:, FI["quiet"]] = R["idle"]
        for w in (1, 3, 10, 30):
            if w <= R["idle"]:
                for f in (["nb1", "ns1", "bsol1", "ssol1", "maxb1", "maxs1"] if w == 1 else [f"{p}{w}" for p in ("nb", "ns", "bsol", "ssol", "net", "nw", "bigb", "bigs", "maxb", "maxs", "dd")]):
                    X[:, FI[f]] = 0
                if w == 10: X[:, [FI["fam_b10"], FI["fam_s10"], FI["bot_b10"], FI["fresh_b10"]]] = 0
                if w == 30: X[:, [FI["dev_s30"], FI["ins_s30"]]] = 0
        for w in (1, 3, 10, 30, 100):
            if w <= R["idle"]: X[:, FI[f"ret{w}"]] = 0
        m = np.ones(len(cand), bool)
        for f, op, v in R["conds"]: m &= opmask(X[:, FI[f]], op, v)
        idx = cand[m]
    else:
        m = np.ones(len(F), bool)
        for f, op, v in R["conds"]:
            m &= opmask(F[:, FI[f]], op, v)
            if not m.any(): break
        idx = np.flatnonzero(m)
    if R["mode"] == "be_trigger" and len(idx):
        # standing in for the trigger buyer is only honest at an UNCONTESTED moment: the token was quiet >= 10 slots and is
        # >= 30 slots old (no launch race). Early-launch "baits" are snipes we cannot place at will.
        idx = idx[(F[idx, FI["quiet"]] >= 10) & (F[idx, FI["age"]] >= 30)]
    if R["special"] and len(idx):
        keep = []
        for k in idx:
            ok = True
            for kind, bid, kk, op, v in R["special"]:
                val = special_val(d, int(k), kind, bid, kk)
                if not opmask(np.array([val]), op, v)[0]: ok = False; break
            if ok: keep.append(k)
        idx = np.array(keep, np.int64)
    return idx

def special_val(d, k, kind, bid, kk):
    a = k - int(d["F"][k, d["FI"]["ntr"]]) + 1                     # first trade index of this token
    b_ = d["bid"]
    if kind == "acted":
        s0 = d["s"][k]; j = k
        while j >= a and d["s"][j] >= s0 - kk:
            if b_[j] == bid: return 1.0
            j -= 1
        return 0.0
    pos = 0.0; pk = 0.0
    for j in range(a, k + 1):
        if b_[j] == bid:
            pos += d["tokn"][j] if d["buy"][j] else -d["tokn"][j]; pk = max(pk, pos)
    return 1.0 if pk > 0 and pos > 0.01 * pk else 0.0

# ------------------------------------------------------------------ one trade
def sim(d, k, R, lat):
    s = d["s"]; arr = d["arr"]; end = int(d["tend"][k]); fr = float(d["fr"][k])
    excl = None
    if R["mode"] == "be_trigger":
        X = float(d["sol"][k]); q = float(d["tokn"][k]); V = float(d["vsol"][k]); T = float(d["vtok"][k])
        B = X * (1 + fr) / 1e9; j = k + 1; land_slot = int(s[k]); land_arr = float(arr[k]); ahead = 0; excl = int(d["uid"][k])
    else:
        if R["event"] == "idle": land_arr = (s[k] + R["idle"]) * SMS + lat
        elif R["race"]: land_arr = float(arr[k]) + lat
        else: land_arr = (s[k] + 1) * SMS + lat
        j = k + 1
        while j < end and arr[j] < land_arr: j += 1
        ahead = j - k - 1
        Vb = float(d["vsol"][j - 1]); Tb = float(d["vtok"][j - 1])
        if Vb >= GRADV or Tb <= 0: return None
        if (Vb / Tb) / (float(d["vsol"][k]) / float(d["vtok"][k])) > GUARD:
            return dict(fail=1, pnl=-FAIL, land=land_arr, exit=land_arr, B=R["size"], hold=0, ahead=ahead)
        B = R["size"]; X = B * 1e9 / (1 + fr); q = Tb * X / (Vb + X); V = Vb + X; T = Tb - q
        land_slot = int(land_arr // SMS)
    p_in = X / q; tp = R["tp"]; sl = R["sl"]; t_end = land_slot + R["max_slots"]
    on = R["on"]; ev_dev = "dev_sell" in on; ev_bs = "big_sell" in on; ev_bb = "big_buy" in on; ev_fs = "fam_sell" in on
    bb_ids = {int(x.split(":")[1]) for x in on if x.startswith("bot_buy:")}; bs_ids = {int(x.split(":")[1]) for x in on if x.startswith("bot_sell:")}
    pend = None; exit_slot = None
    CH = 512
    while j < end:
        hi = min(end, j + CH)
        S_ = s[j:hi].tolist(); BU = d["buy"][j:hi].tolist(); SO = d["sol"][j:hi].tolist(); TK = d["tokn"][j:hi].tolist()
        SL_ = d["slack"][j:hi].tolist(); WT_ = d["wt"][j:hi].tolist(); BID = d["bid"][j:hi].tolist()
        UID = d["uid"][j:hi].tolist() if excl is not None else None
        for t in range(hi - j):
            st = S_[t]
            if pend is not None and st > pend: exit_slot = pend; break
            if st > t_end: exit_slot = t_end; break
            if UID is not None and UID[t] == excl: continue
            if BU[t]:
                sol = SO[t]; dt = T * sol / (V + sol)
                if dt < TK[t] / (1.0 + SL_[t]): continue                       # this follower's slippage limit fails now
                Vn = V + sol; Tn = T - dt
                if Vn >= GRADV: exit_slot = st; break
                V, T = Vn, Tn
                if ev_bb and sol >= 0.5e9 and pend is None: pend = st
                if bb_ids and BID[t] in bb_ids and pend is None: pend = st
            else:
                tk = TK[t]; so = V * tk / (T + tk); V -= so; T += tk
                if pend is None and ((ev_bs and SO[t] >= 0.5e9) or (ev_dev and WT_[t] == 1) or (ev_fs and WT_[t] >= 11) or (bs_ids and BID[t] in bs_ids)): pend = st
            if pend is None and (tp or sl):
                mlt = (V / T) / p_in
                if (tp and mlt >= tp) or (sl and mlt <= sl): pend = st
        if exit_slot is not None: break
        j = hi
    if exit_slot is None: exit_slot = pend if pend is not None else min(t_end, int(s[end - 1]) if end > 0 else t_end)
    got = V * q / (T + q) * (1 - fr) / 1e9
    return dict(fail=0, pnl=got - B - FIX, land=land_arr, exit=(exit_slot + 1) * SMS, B=B, hold=exit_slot - land_slot, ahead=ahead)

# ------------------------------------------------------------------ evaluate a rule on one day / latency
def evaluate(d, R, lat, idx=None, unc_cap=2500, keep=False):
    if idx is None: idx = triggers(d, R)
    out = dict(trig=int(len(idx)))
    if not len(idx): return out
    order = idx[np.argsort(d["arr"][idx], kind="stable")]
    busy = -1.0; acc = []
    for k in order:
        k = int(k)
        if d["arr"][k] + (0 if R["mode"] == "be_trigger" else lat) < busy: continue
        r = sim(d, k, R, lat)
        if r is None: continue
        r["k"] = k; acc.append(r)
        if not r["fail"]: busy = r["exit"]
    # unconstrained sample (every trigger, evenly thinned)
    step = max(1, len(order) // unc_cap); unc = []
    for k in order[::step]:
        r = sim(d, int(k), R, lat)
        if r is not None: unc.append(r)
    def stats(rs, prefix):
        if not rs: return {f"{prefix}n": 0}
        p = np.array([r["pnl"] for r in rs]); ok = [r for r in rs if not r["fail"]]
        B = sum(r["B"] for r in ok) or 1e-9
        sd = p.std(ddof=1) if len(p) > 1 else 0
        top = np.sort(p)[::-1]; ex1 = p.sum() - top[:max(1, len(p) // 100)].sum()
        o = {f"{prefix}n": len(rs), f"{prefix}fail": len(rs) - len(ok), f"{prefix}pnl": round(float(p.sum()), 3), f"{prefix}mean": round(float(p.mean()), 5),
             f"{prefix}per_sol": round(float(p.sum()) / B, 4), f"{prefix}win": round(float((p > 0).mean()), 3), f"{prefix}med": round(float(np.median(p)), 5),
             f"{prefix}t": round(float(p.mean() / (sd / math.sqrt(len(p)))) if sd > 0 else 0.0, 2), f"{prefix}ex1": round(float(ex1), 3)}
        return o
    out.update(stats(acc, "")); out.update(stats(unc, "u_"))
    if acc:
        ks = np.array([r["k"] for r in acc])
        out["dip_overlap"] = round(float(d["dipbot"][ks].mean()), 3); out["f7_overlap"] = round(float(d["f7"][ks].mean()), 3)
        out["hold_med"] = float(np.median([r["hold"] for r in acc if not r["fail"]] or [0])); out["ahead_med"] = float(np.median([r["ahead"] for r in acc]))
        out["tokens"] = int(len(set(d["tok"][ks].tolist())))
        out["per_hour"] = round(float(len(acc) / ((d["arr"].max() - d["arr"].min()) / 3.6e6)), 2)
        if keep: out["ks"] = [int(r["k"]) for r in acc if not r["fail"]]; out["pnls"] = [round(r["pnl"], 5) for r in acc if not r["fail"]]
    return out

def lats(R): return (35, 50) if R["race"] else (35,)

def run_rule(args):
    i, R, days = args[:3]; keep = args[3] if len(args) > 3 else False
    res = {}
    for run in days:
        d = DAYS[run]
        idx = triggers(d, R)
        for lat in lats(R):
            res[f"{run}_{lat}"] = evaluate(d, R, lat, idx, keep=keep)
    return i, res

def load(days):
    for r in days:
        if r not in DAYS: DAYS[r] = load_day(r)

def evaluate_rules(rules, days=("R2", "R3"), procs=9, keep=False):
    from multiprocessing import get_context
    load(days)
    ctx = get_context("fork"); out = {}
    with ctx.Pool(procs) as p:
        for i, res in p.imap_unordered(run_rule, [(i, R, days, keep) for i, R in enumerate(rules)], chunksize=1):
            out[i] = res
    return out

if __name__ == "__main__":
    # sanity baselines
    load(["R2", "R3"])
    M = DAYS["R2"]["M"]
    base = [
        {"name": "BASE dip-bot trigger (no selection), 6-slot exit", "event": "sell", "when": [["sol", ">=", 1.08], ["move", "<=", -4.65], ["age", "<=", 1623]], "race": True, "size": 0.5, "exit": {"max_slots": 6}},
        {"name": "BASE F7 bait (be the trigger), 100-slot exit", "event": "buy", "mode": "be_trigger", "when": [["sol", ">=", 0.9], ["sol", "<=", 3], ["quiet", ">=", 20], ["age", ">=", 150], ["curve", "<=", 47], ["wt", "not_in", ["creator", "insider"]]], "race": False, "exit": {"max_slots": 100}},
        {"name": "BASE big-buy follow at our speed, 4-slot exit", "event": "buy", "when": [["sol", ">=", 0.5], ["ret10", ">=", 10], ["net3", ">=", 1], ["curve", ">=", 33], ["curve", "<=", 60], ["age", ">=", 8]], "race": True, "size": 0.5, "exit": {"max_slots": 4}},
        {"name": "BASE idle 50 slots buy (no bait credit), 100-slot exit", "event": "idle", "idle_slots": 50, "when": [["age", ">=", 150], ["curve", "<=", 40]], "size": 0.5, "exit": {"max_slots": 100}},
    ]
    rules = [compile_rule(r, M["feats"], M["themes"], M["xl"]) for r in base]
    import time; t0 = time.time()
    res = evaluate_rules(rules, ("R2", "R3"), procs=4)
    for i, R in enumerate(rules):
        print(R["name"])
        for k, v in res[i].items(): print("   ", k, {kk: vv for kk, vv in v.items() if kk in ("trig", "n", "fail", "pnl", "mean", "per_sol", "win", "t", "ex1", "u_n", "u_mean", "u_per_sol", "hold_med", "ahead_med", "per_hour", "dip_overlap", "f7_overlap")})
    print(f"{time.time() - t0:.0f}s")

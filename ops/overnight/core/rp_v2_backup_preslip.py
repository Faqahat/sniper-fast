#!/usr/bin/env python3
# REPLAY ENGINE (read-only, offline, no money): exact pump.fun bonding-curve replay of everyone's real trades with OUR buy
# inserted at our REAL place in line and our sells (full or partial) inserted where they would land.
#  - place in line: our engine's arrival timeline (shadow "obs": every outside tx it saw, ms after the create). Outside
#    txs seen before our landing ms are matched to their chain trades; we go right after the last of them in chain order
#    (and never ahead of the creator / glued bundle). Launches without a timeline are skipped (no honest fill).
#  - slippage cap: if our fill price is above the cap vs the price after the creator's own buy, the buy FAILS (costs the
#    failed-tx fee only) - like real snipers' slippage failures.
#  - exits: legs of (fraction, trigger); a trigger seen on a trade fills at the END of that trade's slot (our sell lands
#    after it) or one slot later (pessimistic); time legs fill at the curve state of that time.
#  - costs: pump fee per side from the events, our buy overhead (priority+tip, % of size), a fixed fee per sell tx,
#    failed-buy fee. The curve after a sell or buy of ours moves every later trade exactly (buyers' SOL in, sellers' tokens).
import os, json, gzip, glob, zlib, math, collections
D = "/home/moiz/sniper-data/collect"
RUNS = {"R1": ("run_20261021_2207", "phaseA"), "R2": ("run_20261022_1543", os.environ.get("RP_PHASEA_R2", "phaseA_fwd"))}
SLOT_MS = 212.0
GRAD_VSOL = 114e9                      # curve complete -> trading moves to the AMM (no price in our data after that)

def bucket(m): return zlib.crc32(m.encode()) % 256

def load_launches():
    L = {}
    for tag, (run, _) in RUNS.items():
        for l in open(os.path.join(D, run, "launches.jsonl")):
            try: c = json.loads(l)
            except Exception: continue
            if c["mint"] not in L: c["run"] = tag; L[c["mint"]] = c
    return L

def load_obs(files=None):
    files = files or [os.path.join(D, "shadow", f) for f in ("scores_v1.jsonl", "scores_v2.jsonl", "scores_v3.jsonl")]
    O = {}
    for f in files:
        if not os.path.exists(f): continue
        for l in open(f):
            try: r = json.loads(l)
            except Exception: continue
            m = r.get("mint")
            if r.get("type") == "decide": O.setdefault(m, {})["dec"] = r
            elif r.get("type") == "obs":
                outs = []
                for x in (r.get("outs") or "").split(","):
                    p = x.split(":")
                    if len(p) >= 4:
                        try: outs.append((float(p[0]), float(p[1]), p[2] == "1", p[3]))
                        except ValueError: pass
                O.setdefault(m, {})["outs"] = outs
    return {m: v for m, v in O.items() if "outs" in v}

def read_bucket(run_tag, b, mints):
    """trade rows for the given mints in one bucket -> {mint: [trade dicts in chain order]}"""
    pa = RUNS[run_tag][1]; out = collections.defaultdict(list); seen = set()
    for f in glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] != "T": continue
                r = json.loads(line)
                m = r[1]
                if m not in mints: continue
                (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                if err or (sig, j) in seen: continue
                seen.add((sig, j))
                out[m].append(dict(s=s, i=i, j=j, bt=bt, sig=sig, payer=payer, user=user, buy=buy == 1, sol=sol, tok=tok, vsol=vsol, vtok=vtok,
                                   fbps=fbps or 95, cbps=cbps or 30, fee=fee, tips=tips))
        except (EOFError, OSError, zlib.error): pass
    for m in out: out[m].sort(key=lambda t: (t["s"], t["i"], t["j"]))
    return out

def structure(tr, c):
    """creator buy index, glued bundle (consecutive buy txs right after the create in the create slot), insiders"""
    S = c["slot"]; ci = c.get("idx"); creator = c.get("creator") or c.get("user"); signer = c.get("user")
    ins = {creator, signer}; g_end = 0; prev = ci; dev_k = None; glued = []
    for k, t in enumerate(tr):
        if t["sig"] == c.get("sig"):
            g_end = k + 1; dev_k = k; continue
        if t["s"] == S and prev is not None and t["i"] in (prev, prev + 1) and t["buy"]:
            glued.append(t); prev = t["i"]; g_end = k + 1
        elif t["s"] == S and prev is not None and t["i"] > prev + 1: break
        elif t["s"] > S: break
    ins |= {t["user"] for t in glued}
    return dict(g_end=g_end, dev_k=dev_k, glued=glued, insiders=ins, creator=creator, signer=signer)

def place(tr, c, st, outs, land_ms, max_slots=6):
    """index in tr where our buy goes (we are BEFORE tr[idx]); matched outside txs seen before land_ms are ahead"""
    S = c["slot"]; used = set(); last = st["g_end"] - 1; n_ahead = 0
    cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    for ms, sol, isbuy, w6 in sorted(outs):
        if ms >= land_ms: break
        for k, t in cand:
            if k in used or not t["user"].startswith(w6): continue
            if t["buy"] != isbuy and not (sol == 0 and not isbuy): continue   # "0.000:0" = undecoded (often a routed BUY): any side
            if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
            used.add(k); last = max(last, k); n_ahead += 1; break
    return max(last + 1, st["g_end"]), n_ahead

# ---------------------------------------------------------------- exits
def R(name, legs, cap_s):  # legs: list of (fraction, trigger); trigger kinds: ("x", mult) ("t", s) ("sl", mult) ("dd", arm, drop) ("ev", kind)
    return dict(name=name, legs=legs, cap=cap_s)

def default_rules():
    rules = []
    for t in (0.3, 1, 2, 3, 5, 10, 20, 30, 60, 120, 300):
        rules.append(R(f"hold{t}s", [(1.0, ("t", t))], t + 1))
    rules.append(R("fsell_out", [(1.0, ("ev", "out_sell"))], 30))
    rules.append(R("fsell_any", [(1.0, ("ev", "any_sell"))], 30))
    rules.append(R("devsell", [(1.0, ("ev", "ins_sell"))], 60))
    for tp in (1.15, 1.3, 1.5, 2.0, 3.0):
        for sl in (0.9, 0.8, 0.7, None):
            for cap in (20, 60, 300):
                legs = [(1.0, ("x", tp))] + ([(1.0, ("sl", sl))] if sl else [])
                rules.append(R(f"tp{tp}_sl{sl}_c{cap}", legs, cap))
    for arm in (1.2, 1.5, 2.0):
        for drop in (0.15, 0.25, 0.4):
            rules.append(R(f"trail{arm}_{drop}", [(1.0, ("dd", arm, drop)), (1.0, ("sl", 0.7))], 600))
    # partial ladders ("monitor the price and sell in pieces")
    rules.append(R("lad_50@1.5_25@2_25@3_sl.7", [(0.5, ("x", 1.5)), (0.25, ("x", 2.0)), (0.25, ("x", 3.0)), (1.0, ("sl", 0.7))], 300))
    rules.append(R("lad_33@1.3_33@1.6_trail", [(0.33, ("x", 1.3)), (0.33, ("x", 1.6)), (1.0, ("dd", 1.6, 0.2)), (1.0, ("sl", 0.75))], 300))
    rules.append(R("lad_25each_1.25_1.5_2_3_sl.8", [(0.25, ("x", 1.25)), (0.25, ("x", 1.5)), (0.25, ("x", 2.0)), (0.25, ("x", 3.0)), (1.0, ("sl", 0.8))], 120))
    rules.append(R("lad_60@1.7_trail.3", [(0.6, ("x", 1.7)), (1.0, ("dd", 1.7, 0.3)), (1.0, ("sl", 0.75))], 600))
    rules.append(R("time_25@5_10_20_40s", [(0.25, ("t", 5)), (0.25, ("t", 10)), (0.25, ("t", 20)), (0.25, ("t", 40))], 41))
    rules.append(R("twap_10pct_every2s_20s", [(0.1, ("t", 2 * k)) for k in range(1, 11)], 21))
    rules.append(R("twap_20pct_every1s_5s", [(0.2, ("t", k)) for k in range(1, 6)], 6))
    rules.append(R("half@1.3_rest_hold60", [(0.5, ("x", 1.3)), (1.0, ("t", 60)), (1.0, ("sl", 0.75))], 61))
    rules.append(R("half@first_sell_rest@2x", [(0.5, ("ev", "out_sell")), (1.0, ("x", 2.0)), (1.0, ("sl", 0.7))], 120))
    return rules

def sim(tr, c, st, idx, B, rules, fee_buy_pct=0.02, sell_fee_sol=0.0005, delay_slots=0, me=None, entry_state=None, fill_pen=0.0, drop_after=None):
    """our buy of B SOL right before tr[idx]; returns {rule: dict(pnl, ret, nsell, hold_s, grad)} + entry info.
    me: wallet whose own trades are removed from the path (validation runs)."""
    S = c["slot"]
    path = [t for t in tr if t["user"] != me] if me else tr
    if me: idx = sum(1 for t in tr[:idx] if t["user"] != me)
    if drop_after: path = path[:idx] + [t for t in path[idx:] if not (t["buy"] and t["user"] in drop_after)]
    if entry_state: V, T = entry_state
    elif idx > 0: V, T = path[idx - 1]["vsol"], path[idx - 1]["vtok"]
    else: V, T = 30_000_000_000, 1_073_000_000_000_000
    if not T or V >= GRAD_VSOL or V < 25e9: return None
    if any((not t["vtok"]) or t["vsol"] > 200e9 or t["vsol"] < 25e9 for t in path[:50]): return None      # non-SOL quote / odd reserves
    fb, cb = path[0]["fbps"], path[0]["cbps"]; fr = (fb + cb) / 1e4
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    q = int(q * (1 - fill_pen))                     # pessimistic fill (validation: model fills ~1.2% better than real on average)
    p_in = X / q                                    # our average curve price (lamports per raw token)
    buy_slot = max(S, path[idx - 1]["s"]) if idx > 0 else S          # we land right after path[idx-1] (verifier fix 2026-10-23)
    cost = B * (1 + fee_buy_pct)
    ins = st["insiders"]
    out = {}
    # state per rule
    RS = []
    for r in rules:
        RS.append(dict(r=r, left=1.0, got=0.0, nsell=0, fired=[False] * len(r["legs"]), peak=1.0, pend=[], done=False, last_s=buy_slot, grad=False))
    def sell_frac(rs, frac, V, T):
        """our sell of frac of the ORIGINAL position at state (V,T) -> new (V,T)"""
        k = int(q * min(frac, rs["left"]))
        if k <= 0: return V, T
        so = V * k // (T + k); rs["got"] += so * (1 - fr) / 1e9 - sell_fee_sol; rs["left"] -= k / q; rs["nsell"] += 1
        return V - so, T + k
    # every rule has its own curve copy (our sells move the curve differently per rule)
    for rs in RS: rs["V"], rs["T"] = V, T
    n = len(path); k = idx
    def legs_due(rs, t_slot, kind_ev=None, mult=None, now_slot=None):
        due = []
        el = (now_slot - buy_slot) * SLOT_MS / 1000.0
        for li, (fr_, trig) in enumerate(rs["r"]["legs"]):
            if rs["fired"][li]: continue
            kd = trig[0]
            if kd == "t" and el >= trig[1]: due.append(li)
            elif kd == "x" and mult is not None and mult >= trig[1]: due.append(li)
            elif kd == "sl" and mult is not None and mult <= trig[1]: due.append(li)
            elif kd == "dd" and mult is not None and rs["peak"] >= trig[1] and mult <= rs["peak"] * (1 - trig[2]): due.append(li)
            elif kd == "ev" and kind_ev and (trig[1] in kind_ev): due.append(li)
        return due
    while k <= n:
        t = path[k] if k < n else None
        ts = t["s"] if t else None
        for rs in RS:
            if rs["done"]: continue
            # pending fills scheduled for the end of slot ps: execute before the first trade of a later slot
            if rs["pend"] and (t is None or ts > rs["pend"][0][0]):
                for _, li in rs["pend"]:
                    if not rs["fired"][li]:
                        rs["fired"][li] = True; rs["V"], rs["T"] = sell_frac(rs, rs["r"]["legs"][li][0] if rs["r"]["legs"][li][1][0] not in ("sl", "dd") else 1.0, rs["V"], rs["T"])
                rs["pend"] = []
                if rs["left"] <= 1e-9: rs["done"] = True; continue
            # time legs / cap: fill at the state before this trade if its slot is past the due time
            now_slot = ts if t is not None else (rs["last_s"] + 10 ** 6)
            el = (now_slot - buy_slot) * SLOT_MS / 1000.0
            if el > rs["r"]["cap"] or t is None:
                for li, (fr_, trig) in enumerate(rs["r"]["legs"]):
                    if not rs["fired"][li] and trig[0] in ("t", "slot") and (t is None or el >= trig[1] or trig[0] == "slot"):
                        rs["fired"][li] = True; rs["V"], rs["T"] = sell_frac(rs, fr_, rs["V"], rs["T"])
                if rs["left"] > 1e-9: rs["V"], rs["T"] = sell_frac(rs, 1.0, rs["V"], rs["T"])
                rs["done"] = True; continue
            for li, (fr_, trig) in enumerate(rs["r"]["legs"]):
                if not rs["fired"][li] and ((trig[0] == "t" and el >= trig[1]) or (trig[0] == "slot" and t is not None and ts > buy_slot + trig[1])):
                    rs["fired"][li] = True; rs["V"], rs["T"] = sell_frac(rs, fr_, rs["V"], rs["T"])
            if rs["left"] <= 1e-9: rs["done"] = True; continue
            # apply the market trade to this rule's curve
            Vr, Tr = rs["V"], rs["T"]
            if t["buy"]:
                dd = Tr * t["sol"] // (Vr + t["sol"]); Vr += t["sol"]; Tr -= dd
            else:
                so = Vr * t["tok"] // (Tr + t["tok"]); Vr -= so; Tr += t["tok"]
            rs["V"], rs["T"] = Vr, Tr; rs["last_s"] = ts
            if (Vr >= GRAD_VSOL or Tr <= 0) and not rs["grad"]:
                rs["grad"] = True                     # curve completes: sell the rest at this (last curve) price, flagged
                rs["V"], rs["T"] = sell_frac(rs, 1.0, rs["V"], rs["T"]); rs["done"] = True; continue
            mult = (Vr / Tr) / p_in
            rs["peak"] = max(rs["peak"], mult)
            ev = set()
            if not t["buy"]:
                ev.add("any_sell")
                ev.add("ins_sell" if t["user"] in ins else "out_sell")
            due = legs_due(rs, ts, ev, mult, ts)
            if due:
                fill_slot = ts + delay_slots
                for li in due:
                    if all(li != p[1] for p in rs["pend"]): rs["pend"].append((fill_slot, li))
        if all(rs["done"] for rs in RS): break
        k += 1
    for rs in RS:
        if not rs["done"] and rs["left"] > 1e-9: rs["V"], rs["T"] = sell_frac(rs, 1.0, rs["V"], rs["T"])
        pnl = rs["got"] - cost
        out[rs["r"]["name"]] = dict(pnl=round(pnl, 6), ret=round(pnl / B, 5), nsell=rs["nsell"], hold_s=round((rs["last_s"] - buy_slot) * SLOT_MS / 1000, 2), grad=rs["grad"])
    return out

def place_ms(tr, c, st, outs, ms, after_idx, max_slots=8):
    """index for a tx of ours that lands at `ms` (our feed clock) and must come after tr[after_idx-1]: right after the
    last matched outside trade that arrived before `ms` (same matching as place())"""
    S = c["slot"]; used = set(); last = after_idx - 1
    cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    for a, sol, isbuy, w6 in sorted(outs):
        if a >= ms: break
        for k, t in cand:
            if k in used or not t["user"].startswith(w6): continue
            if t["buy"] != isbuy and not (sol == 0 and not isbuy): continue   # "0.000:0" = undecoded (often a routed BUY): any side
            if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
            used.add(k); last = max(last, k); break
    return max(last + 1, after_idx)

def flip(tr, idx_buy, idx_sell, B, fee_buy_pct=0.02, sell_fee_sol=0.0005, fill_pen=0.015):
    """buy B SOL right before tr[idx_buy], sell everything right before tr[idx_sell] (idx_sell >= idx_buy). Net SOL PnL."""
    V, T = (tr[idx_buy - 1]["vsol"], tr[idx_buy - 1]["vtok"]) if idx_buy > 0 else (30e9, 1.073e15)
    fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
    X = int(B * 1e9 / (1 + fr)); q = int(T * X // (V + X)); V += X; T -= q; q = int(q * (1 - fill_pen))
    for t in tr[idx_buy:idx_sell]:
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        if V >= GRAD_VSOL: break
    so = V * q // (T + q)
    return so * (1 - fr) / 1e9 - sell_fee_sol - B * (1 + fee_buy_pct)

SS = None
def place_proxy(tr, c, st, land_ms, slot_ms=SLOT_MS):
    """landing proxy WITHOUT our arrival timeline (old data): a tx's arrival ~ its position inside the block (index / block
    size, block size estimated from the collector), slots of SLOT_MS. Outside trades with proxy arrival < land_ms are ahead."""
    global SS
    if SS is None: SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize.json")).items()}
    S = c["slot"]; ci = c.get("idx") or 0; nS = max(SS.get(S, 400), ci + 1)
    def arr(t):
        if t["s"] == S: return (t["i"] - ci) / nS * slot_ms
        ms = (nS - ci) / nS * slot_ms
        for s in range(S + 1, t["s"]): ms += slot_ms
        return ms + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * slot_ms
    last = st["g_end"] - 1; n = 0
    for k, t in enumerate(tr):
        if k < st["g_end"] or t["user"] in st["insiders"]: continue
        if t["s"] - S > 6: break
        if arr(t) < land_ms: last = max(last, k); n += 1
    return max(last + 1, st["g_end"]), n

def place_imputed(tr, c, st, outs, land_ms, max_slots=6):
    """conservative placement: outside trades our engine did NOT see (~15% of create-slot buys, mostly routed through
    other programs) get an imputed arrival = the arrival of the next SEEN trade after them in chain order (or the
    previous one + 1 ms when none follows). Everything with (seen or imputed) arrival < land_ms is ahead of us."""
    S = c["slot"]; used = set(); seen_ms = {}
    cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    for a, sol, isbuy, w6 in sorted(outs):
        for k, t in cand:
            if k in used or not t["user"].startswith(w6): continue
            if t["buy"] != isbuy and not (sol == 0 and not isbuy): continue   # "0.000:0" = undecoded (often a routed BUY): any side
            if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
            used.add(k); seen_ms[k] = a; break
    ks = [k for k, _ in cand]; arr = {}
    nxt = None
    for k in reversed(ks):
        if k in seen_ms: nxt = seen_ms[k]
        arr[k] = seen_ms.get(k, nxt)
    prev = None
    for k in ks:
        if arr[k] is None: arr[k] = (prev + 1.0) if prev is not None else 1e9
        prev = arr[k] if k in seen_ms else prev
    last = st["g_end"] - 1; n = 0
    for k in ks:
        if arr[k] < land_ms: last = max(last, k); n += 1
    return max(last + 1, st["g_end"]), n

def shift(tr, c, st, idx, k, max_slots=1):
    """pessimistic: move our buy k OUTSIDE trades later (only trades within max_slots of the create), i.e. k more
    competitors land ahead of us than the arrival model says"""
    S = c["slot"]; j = idx; moved = 0
    while moved < k and j < len(tr) and tr[j]["s"] - S <= max_slots:
        if tr[j]["user"] not in st["insiders"]: moved += 1
        j += 1
    return j

def place_bo(tr, c, st, outs, land_ms, max_slots=6):
    """BLOCK-ORDER-CONSISTENT placement (independent verifier's rule, 2026-10-23): a trade our engine saw is ahead if it
    arrived before land_ms; a trade it never saw is ahead if a LATER trade in block order (which therefore arrived
    after it) was seen before land_ms. Unseen trades with no such bound stay behind us (cannot be placed)."""
    S = c["slot"]; used = set(); seen = {}
    cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    for a, sol, isbuy, w6 in sorted(outs):
        for k, t in cand:
            if k in used or not t["user"].startswith(w6): continue
            if t["buy"] != isbuy and not (sol == 0 and not isbuy): continue
            if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
            used.add(k); seen[k] = a; break
    ub = {}; cur = float("inf")
    for k, _ in reversed(cand):
        if k in seen: cur = min(cur, seen[k])
        ub[k] = cur
    last = st["g_end"] - 1; n = 0
    for k, _ in cand:
        a = seen.get(k)
        if (a is not None and a < land_ms) or (a is None and ub[k] < land_ms): last = max(last, k); n += 1
    return max(last + 1, st["g_end"]), n

def read_failed(run_tag, b, mints):
    """failed txs touching the given mints (phase-A 'X' rows with err=1): {mint: [(slot, idx, signer)]} — arrival
    anchors for block-order placement (our engine sees failed txs too, before they fail)"""
    pa = RUNS[run_tag][1]; out = collections.defaultdict(list); seen = set()
    for f in glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] != "X": continue
                r = json.loads(line)
                m = r[1]
                if m not in mints or r[12] != 1 or r[5] in seen: continue
                seen.add(r[5]); out[m].append((r[2], r[3], r[6] or ""))
        except (EOFError, OSError, zlib.error): pass
    return out

def place_bo2(tr, c, st, outs, land_ms, failed=(), max_slots=6):
    """block-order placement using BOTH successful trades and failed txs as arrival anchors: every outs entry is matched
    to a successful trade or a failed tx of that wallet; an unseen successful trade is ahead of us if anything after it
    in block order (slot, index) was seen before land_ms."""
    S = c["slot"]
    succ = [(t["s"], t["i"], k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    fl = [(s, i, None, u) for s, i, u in failed if s - S <= max_slots and u not in st["insiders"]]
    used_s = set(); used_f = set(); seen = {}            # key (slot, idx) -> arrival ms
    for a, sol, isbuy, w6 in sorted(outs):
        hit = None
        for s, i, k, t in succ:
            if k in used_s or not t["user"].startswith(w6): continue
            if t["buy"] != isbuy and not (sol == 0 and not isbuy): continue
            if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
            used_s.add(k); hit = (s, i); break
        if hit is None:
            for s, i, _, u in fl:
                if (s, i) in used_f or not u.startswith(w6): continue
                used_f.add((s, i)); hit = (s, i); break
        if hit is not None: seen[hit] = min(a, seen.get(hit, a))
    anchors = sorted(seen.items())                         # [((s, i), ms)] in block order
    last = st["g_end"] - 1; n = 0
    for s, i, k, t in succ:
        a = seen.get((s, i))
        if a is None:                                      # upper bound: earliest arrival among anchors after it in block order
            later = [ms for (ss, ii), ms in anchors if (ss, ii) > (s, i)]
            a = min(later) if later else None
            if a is None or a >= land_ms: continue
        elif a >= land_ms: continue
        last = max(last, k); n += 1
    return max(last + 1, st["g_end"]), n


def sim_flow(tr, c, st, idx, B, min_net_sol, max_extra, first_slot=1, fee_buy_pct=0.02, sell_fee_sol=0.0005, fill_pen=0.015):
    """momentum exit: sell all at the end of the first slot (>= buy slot + first_slot) whose net SOL flow (all other
    traders' buys - sells) is below min_net_sol, holding at most max_extra extra slots. Net SOL PnL."""
    S = c["slot"]; path = tr
    V, T = (path[idx - 1]["vsol"], path[idx - 1]["vtok"]) if idx > 0 else (30e9, 1.073e15)
    fr = (path[0]["fbps"] + path[0]["cbps"]) / 1e4
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - fill_pen))
    buy_slot = max(S, path[idx - 1]["s"]) if idx > 0 else S
    sell_slot = buy_slot + first_slot; last_allowed = buy_slot + first_slot + max_extra
    k = idx; net = collections.Counter()
    while k < len(path):
        t = path[k]
        if t["s"] > sell_slot:
            # decide at the end of sell_slot: extend if that slot's flow was strong
            if net[sell_slot] >= min_net_sol * 1e9 and sell_slot < last_allowed:
                sell_slot += 1; continue
            break
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; net[t["s"]] += t["sol"]
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]; net[t["s"]] -= so
        if V >= GRAD_VSOL: break
        k += 1
    so = V * q // (T + q)
    return so * (1 - fr) / 1e9 - sell_fee_sol - B * (1 + fee_buy_pct)

def sim_dg(tr, c, st, idx, B, light_frac, light_slot, steps, twap_every, twap_frac, twap_max_s, stop_mult=None, tp=None,
           fee_buy_pct=0.02, sell_fee_sol=0.0005, fill_pen=0.015, min_sell_sol=0.005):
    """DGmspi-style ladder (seen on chain 2026-10-23): a 'lightning' sell of light_frac of the position at the end of slot
    (buy slot + light_slot); fixed steps [(slot_offset, frac_of_REMAINING)]; then every twap_every slots sell twap_frac
    of what is LEFT until twap_max_s seconds (then the rest); optional stop (price <= stop_mult x entry -> sell all) and
    take-profit steps tp=[(mult, frac_of_remaining)] fired once each when the price first reaches mult. Each sell lands at
    the end of its slot. Sells smaller than min_sell_sol are skipped (merged into the next). Net SOL PnL, number of sells."""
    S = c["slot"]
    V, T = (tr[idx - 1]["vsol"], tr[idx - 1]["vtok"]) if idx > 0 else (30e9, 1.073e15)
    fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; p_in = X / q; q = int(q * (1 - fill_pen))
    buy_slot = max(S, tr[idx - 1]["s"]) if idx > 0 else S
    left = q; got = 0.0; nsell = 0; tp = list(tp or []); done_tp = set()
    sched = {buy_slot + light_slot: ("frac_pos", light_frac)}
    for so_, f_ in steps: sched[buy_slot + so_] = ("frac_left", f_)
    end_slot = buy_slot + int(twap_max_s * 1000 / SLOT_MS)
    first_twap = max([buy_slot + light_slot] + [buy_slot + s for s, _ in steps]) + twap_every
    def sell(k, V, T):
        nonlocal left, got, nsell
        k = min(int(k), left)
        if k <= 0: return V, T
        so = V * k // (T + k)
        if so * (1 - fr) / 1e9 < min_sell_sol and k < left: return V, T
        got += so * (1 - fr) / 1e9 - sell_fee_sol; left -= k; nsell += 1
        return V - so, T + k
    cur = buy_slot; k = idx; pend_stop = False; pend_tp = []
    while left > 0:
        # end of slot `cur`: apply this slot's trades, then our scheduled / triggered sells for this slot
        while k < len(tr) and tr[k]["s"] <= cur:
            t = tr[k]
            if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
            else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
            k += 1
            mult = (V / T) / p_in
            if stop_mult and mult <= stop_mult: pend_stop = True
            for j, (m_, f_) in enumerate(tp):
                if j not in done_tp and mult >= m_: done_tp.add(j); pend_tp.append(f_)
        if V >= GRAD_VSOL or k >= len(tr) and cur >= end_slot: V, T = sell(left, V, T); break
        if pend_stop: V, T = sell(left, V, T); break
        for f_ in pend_tp: V, T = sell(left * f_, V, T)
        pend_tp = []
        a = sched.get(cur)
        if a: V, T = sell((q * a[1]) if a[0] == "frac_pos" else (left * a[1]), V, T)
        if cur >= first_twap and (cur - first_twap) % twap_every == 0: V, T = sell(left * twap_frac, V, T)
        if cur >= end_slot: V, T = sell(left, V, T); break
        cur += 1
        if k >= len(tr) and cur > end_slot: V, T = sell(left, V, T); break
    return got - B * (1 + fee_buy_pct), nsell

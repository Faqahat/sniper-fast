#!/usr/bin/env python3
# SELECTION STUDY dataset v3 (sel/selexit2.py): selexit.py + TP/SL time limits 6 and 8 slots + incremental cohort features
# (DIP_COHORT_FILE, cohort from TRAIN hours: sel/cohort_train.json). Was: SELECTION STUDY dataset WITH TP / SL / TIME-LIMIT EXITS (sel/selexit.py) = sel/selbuild.py + for every entry delay L an exit grid
# from ONE replay of the position held up to 60 slots (same follower model as rt_tpsl / rt_fixed): fixed holds, and take-profit /
# stop-loss / time-limit exits with a minimum hold (a TP/SL sell lands the slot after the trigger, SELL_LAT ms in). -> sel_exits.npy
# (rows in the same order as the jsonl). Grid names in sel_exits_grid.json. Base dataset notes:
#  - lab: for each target wallet (HkQ7hMjy, DYXDDrZC, haqqiUUX) the delay in ms (block-position proxy) of its first buy after the
#    dump, if within 1000 ms; dipbuy5 events are first-big-sell-per-slot, so a wallet's buy is credited to the latest dump before it
#  - prev_sell_ms: proxy ms since the previous >=1 SOL sell on the token (to tell clustered dumps apart)
#  - tok: token-level facts at the dump (creator, launch slot index, n trades so far, max vsol so far, seconds since the last buy)
# Run with DIP_MAX_AGE=1800 DIP_BUSY=0 DIP_HS=4 DIP_LATS=20,35,50,75 (no spacing; spacing is applied when evaluating a config).
import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"
import rp
from multiprocessing import Pool
B = float(os.environ.get("DIP_B", "0.5")); TXC = float(os.environ.get("TXC", "0.0008")); PEN = float(os.environ.get("PEN", "0")); MIN_SELL = float(os.environ.get("DIP_MIN_SELL", "1.0")) * 1e9; MAX_AGE = float(os.environ.get("DIP_MAX_AGE", "120"))
LATS = tuple(int(x) for x in os.environ.get("DIP_LATS", "0,20,35,50,75,100,150").split(",")); SMS = rp.SLOT_MS
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
HK = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
TARGETS = ("HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq")
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
def arr(t): return t["s"] * SMS + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * SMS
SLIPIMP = os.environ.get("SLIPIMP") == "1"
if SLIPIMP:
    import hashlib
    _rows = json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"]
    SLACK = sorted(sl for _, sl, _ in _rows)              # empirical slack of decoded follower limits (verifier a8)
def slack(sig):
    h = int(hashlib.sha256(("dip" + sig).encode()).hexdigest()[:8], 16) / 2 ** 32
    return SLACK[min(len(SLACK) - 1, int(h * len(SLACK)))]
DROP = set(json.load(open(os.environ["DIP_DROP_FILE"]))) if os.environ.get("DIP_DROP_FILE") else set()
COH = set(json.load(open(os.environ["DIP_COHORT_FILE"]))) if os.environ.get("DIP_COHORT_FILE") else set()
HSET = tuple(int(x) for x in os.environ.get("DIP_HS", "4,6,8,12").split(","))
HLAG = float(os.environ.get("DIP_HLAG", "0"))
MIN_VSOL = float(os.environ.get("DIP_MIN_VSOL", "0")) * 1e9
REAL = {}
if os.environ.get("DIP_REAL_SLIP") == "1":
    for _l in list(open("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl")) + (list(open("/home/moiz/sniper/ops/overnight/sel/slip_args_sel.jsonl")) if os.environ.get("SEL_SLIP") == "1" else []):
        try: _r = json.loads(_l)
        except Exception: continue
        if _r.get("kind") in ("sol", "tok"): REAL[_r["sig"]] = (_r["kind"], _r["a1"], _r["a2"])
def rt_fixed(tr, ke, fr, H, s_land=None):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land) if s_land is not None else tr[ke - 1]["s"]; frs = fr          # verifier bug 1
    SL = float(os.environ.get("SELL_LAT", "0"))
    for t in tr[ke:]:
        if t["s"] >= s_in + H and (SL <= 0 or t["s"] > s_in + H or (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS >= SL): break
        if t["buy"] and DROP and t["user"] in DROP: continue          # stress variant: these wallets' buys after our entry never happen
        if t["buy"] and t["sig"] in REAL and not t.get("syn"):          # the follower's REAL decoded limit (slip_fetch.py)
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: continue
                V += t["sol"]; T -= d
            else:
                if a1 >= T: continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: continue
                V += cst; T -= a1
        elif t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue    # this follower's min-tokens-out fails after our buy
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)
def rt_tp2(tr, ke, fr, tp, H, s_land=None):
    """take-profit exit with the same follower model as rt_fixed: once our position is worth >= tp x cost (net of fees), the
    sell lands in the next slot SELL_LAT ms in; otherwise the fixed exit at H slots (= rt_fixed)."""
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land) if s_land is not None else tr[ke - 1]["s"]; frs = fr
    SL = float(os.environ.get("SELL_LAT", "0")); s_out = s_in + H; cost = B + TXC
    for t in tr[ke:]:
        if t["s"] >= s_out and (SL <= 0 or t["s"] > s_out or (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS >= SL): break
        if t["buy"] and DROP and t["user"] in DROP: continue
        if t["buy"] and t["sig"] in REAL and not t.get("syn"):
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: continue
                V += t["sol"]; T -= d
            else:
                if a1 >= T: continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: continue
                V += cst; T -= a1
        elif t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
        if s_out > t["s"] + 1 and ((V * q // (T + q)) * (1 - frs) / 1e9 - TXC) / cost >= tp: s_out = t["s"] + 1     # take profit: sell lands next slot
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)
TPS = [tuple(float(v) for v in x.split(":")) for x in os.environ.get("DIP_TPS", "").split(",") if x]
def rt_ev(tr, ke, fr, XS, DD, HMAX, s_land=None, D=None):
    """event exit (learned from DYXDDrZC): hold until another wallet sells >= XS SOL, or the price falls below DD x the peak
    since entry; our sell then lands D ms (block-position proxy) after that trade; cap HMAX slots (fixed exit there)."""
    D = float(os.environ.get("EV_SELL_MS", "60")) if D is None else D
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land) if s_land is not None else tr[ke - 1]["s"]; frs = fr
    SL = float(os.environ.get("SELL_LAT", "0")); s_out = s_in + HMAX; t_out = None; peak = V / T
    for t in tr[ke:]:
        if t_out is not None and arr(t) >= t_out: break
        if t_out is None and t["s"] >= s_out and (SL <= 0 or t["s"] > s_out or (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS >= SL): break
        if t["buy"] and DROP and t["user"] in DROP: continue
        if t["buy"] and t["sig"] in REAL and not t.get("syn"):
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: continue
                V += t["sol"]; T -= d
            else:
                if a1 >= T: continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: continue
                V += cst; T -= a1
        elif t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
        if t_out is None and t["s"] >= s_in and ((not t["buy"] and t["sol"] >= XS * 1e9 and not t.get("syn")) or (V / T) < DD * peak):
            t_out = arr(t) + D
        peak = max(peak, V / T)
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)
EVX = [tuple(float(v) for v in x.split(":")) for x in os.environ.get("DIP_EVX", "").split(",") if x]
FOLLOW = set(json.load(open(os.environ["DIP_FOLLOW_FILE"]))) if os.environ.get("DIP_FOLLOW_FILE") else set()
def rt_tpsl(tr, ke, fr, TP, SL, HMAX, s_land=None):
    """HkQ7hMjy-style exit: take profit when our position is worth >= (1+TP) x cost, stop loss when <= (1-SL) x cost (both net of
    fees), else sell at HMAX slots; the triggered sell lands in the next slot SELL_LAT ms in. Same follower model as rt_fixed."""
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land) if s_land is not None else tr[ke - 1]["s"]; frs = fr
    SLm = float(os.environ.get("SELL_LAT", "0")); s_out = s_in + HMAX; cost = B + TXC
    for t in tr[ke:]:
        if t["s"] >= s_out and (SLm <= 0 or t["s"] > s_out or (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS >= SLm): break
        if t["buy"] and t["sig"] in REAL and not t.get("syn"):
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: continue
                V += t["sol"]; T -= d
            else:
                if a1 >= T: continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: continue
                V += cst; T -= a1
        elif t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
        if s_out > t["s"] + 1:
            val = ((V * q // (T + q)) * (1 - frs) / 1e9 - TXC) / cost
            if val >= 1 + TP or val <= 1 - SL: s_out = t["s"] + 1
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)

import numpy as np
FIXED = (2, 3, 4, 6, 8, 10, 15, 20, 30, 40, 60)
TPG = (0.05, 0.08, 0.12, 0.2, 0.3, 9.0); SLG = (0.05, 0.1, 0.2, 9.0); CAPG = (6, 8, 10, 20, 30, 60); MINHG = (1, 3)
GRID = [("H", h) for h in FIXED] + [("T", tp, sl, cap, mh) for mh in MINHG for cap in CAPG for tp in TPG for sl in SLG]
HMAXP = 60
def rt_path(tr, ke, fr, s_land):
    """our 0.5 SOL position replayed trade by trade up to HMAXP slots (follower model = rt_tpsl + DROP); returns s_in, slot per
    trade, landing key per trade (2*slot + 1 if the trade sits >= SELL_LAT ms into its slot), value/cost after each trade, whether
    a TP/SL check runs after it, and the P&L of selling at each state (index 0 = right after our buy)."""
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land); frs = fr; SLm = float(os.environ.get("SELL_LAT", "0")); s_end = s_in + HMAXP; cost = B + TXC
    S_, K_, VAL, CHK = [], [], [], []; PNL = [(V * q / (T + q)) * (1 - frs) / 1e9 - TXC - cost]
    for t in tr[ke:]:
        pos = (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS
        if t["s"] > s_end or (t["s"] == s_end and (SLm <= 0 or pos >= SLm)): break
        S_.append(t["s"]); K_.append(2 * t["s"] + (1 if (SLm <= 0 or pos >= SLm) else 0)); applied = True
        if t["buy"] and DROP and t["user"] in DROP: applied = False
        elif t["buy"] and t["sig"] in REAL and not t.get("syn"):
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: applied = False
                else: V += t["sol"]; T -= d
            else:
                if a1 >= T: applied = False
                else:
                    cst = V * a1 // (T - a1) + 1
                    if cst * (1 + fr) > a2: applied = False
                    else: V += cst; T -= a1
        elif t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): applied = False
            else: V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        if applied: frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        so = V * q / (T + q)
        PNL.append(so * (1 - frs) / 1e9 - TXC - cost); VAL.append((so * (1 - frs) / 1e9 - TXC) / cost)
        if V >= 110e9: CHK.append(False); break
        CHK.append(applied)
    return s_in, np.array(S_, np.int64), np.array(K_, np.int64), np.array(VAL), np.array(CHK, bool), np.array(PNL)
def exit_grid(s_in, S_, K_, VAL, CHK, PNL):
    n = len(K_)
    def land(s_out): return PNL[min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)]
    out = [land(s_in + h) for h in FIXED]
    hit = {}
    for tp in TPG:
        for sl in SLG: hit[(tp, sl)] = CHK & ((VAL >= 1 + tp) | (VAL <= 1 - sl))
    for mh in MINHG:
        for cap in CAPG:
            co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
            for tp in TPG:
                for sl in SLG:
                    c = hit[(tp, sl)] & win
                    out.append(land(int(S_[int(np.argmax(c))]) + 1) if c.any() else land(co))
    return out
TPSL = [tuple(float(v) for v in x.split(":")) for x in os.environ.get("DIP_TPSL", "").split(",") if x]
FOLX = [tuple(float(v) for v in x.split(":")) for x in os.environ.get("DIP_FOLX", "").split(",") if x]
def rt_follow(tr, k, ke, fr, D, HMAX, s_land=None, H0=2):
    """ride with a pro: if a wallet from FOLLOW bought after the trigger (before us, or within our first slot), hold until the
    first such pro sells, then our sell lands D ms after its sell (cap HMAX slots). No pro in the trade: the fixed H0 exit."""
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land) if s_land is not None else tr[ke - 1]["s"]; frs = fr
    SL = float(os.environ.get("SELL_LAT", "0"))
    pros = {x["user"] for x in tr[k + 1:ke] if x["buy"] and x["user"] in FOLLOW}
    s_out = s_in + (HMAX if pros else H0); t_out = None
    for t in tr[ke:]:
        if t_out is not None and arr(t) >= t_out: break
        if t_out is None and t["s"] >= s_out and (SL <= 0 or t["s"] > s_out or (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS >= SL): break
        if t["buy"] and t["user"] in FOLLOW and t["s"] <= s_in and not pros: pros.add(t["user"]); s_out = s_in + HMAX
        if t["buy"] and t["sig"] in REAL and not t.get("syn"):
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: continue
                V += t["sol"]; T -= d
            else:
                if a1 >= T: continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: continue
                V += cst; T -= a1
        elif t["buy"] and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
        if t_out is None and pros and not t["buy"] and t["user"] in pros: t_out = arr(t) + D
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)
def rt_tp(tr, ke, fr, tp=1.05, hmax=30):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = tr[ke - 1]["s"]; frs = fr; trig = None; cost = B + TXC
    for t in tr[ke:]:
        if trig is not None and t["s"] > trig: break
        if t["s"] >= s_in + hmax: break
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
        if trig is None and ((V * q // (T + q)) * (1 - frs) / 1e9 - TXC) / cost >= tp: trig = t["s"]
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - cost
def work(key):
    run, b = key; out = []; hk = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem") or "InitializeMayhemState" in (c.get("ixn") or []): continue        # verifier bug 2: the field was absent
        S = c["slot"]; st = rp.structure(tr, c); busy = -1
        cbS = set(); cbal = collections.defaultdict(int); csol = 0          # running cohort state over tr[:k] (incremental coh_* features)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; pbp = ge["vsol"] / ge["vtok"]
        for k, t in enumerate(tr):
            if COH and k > 0:
                x = tr[k - 1]
                if x["user"] in COH:
                    if x["buy"]: cbS.add(x["user"]); cbal[x["user"]] += x["tok"]; csol += x["sol"]
                    else: cbal[x["user"]] -= x["tok"]
            # HkQ7hMjy speed check: its buy right after a big sell -> proxy delay
            if t["user"] == HK and t["buy"] and k > 0 and not tr[k - 1]["buy"] and tr[k - 1]["sol"] >= MIN_SELL:
                hk.append(round(arr(t) - arr(tr[k - 1]), 2))
            if t["buy"] or t["sol"] < MIN_SELL or t.get("syn") or k < st["g_end"]: continue
            age = (t["s"] - S) * SMS / 1000
            if age < 1 or age > MAX_AGE or t["vsol"] >= 100e9 or t["vsol"] < MIN_VSOL or t["s"] <= busy: continue
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            a0 = arr(t); kv = k
            while HLAG > 0 and kv > 0 and arr(tr[kv - 1]) >= a0 - HLAG: kv -= 1
            p_before = (t["vsol"] + t["sol"]) / (t["vtok"] - t["tok"]); p_after = t["vsol"] / t["vtok"]; f_sol = t["sol"]; f_vsol = t["vsol"]
            if HLAG > 0 and kv < k and kv > 0:          # the engine only knows the curve as of the last visible trade
                V0, T0 = tr[kv - 1]["vsol"], tr[kv - 1]["vtok"]; so = V0 - V0 * T0 // (T0 + t["tok"])
                p_before = V0 / T0; p_after = (V0 - so) / (T0 + t["tok"]); f_sol = so; f_vsol = V0 - so
            w20 = [x for x in tr[max(0, kv - 60):kv] if t["s"] - x["s"] <= 20]
            peak = max([x["vsol"] / x["vtok"] for x in tr[:kv]] + [p_after])
            # richer causal features (state up to and including the sell)
            su = t["user"]; sb = [x for x in tr[:kv] if x["user"] == su]
            s_tok_b = sum(x["tok"] for x in sb if x["buy"]); s_tok_s = sum(x["tok"] for x in sb if not x["buy"])
            s_sol_b = sum(x["sol"] for x in sb if x["buy"]); s_sol_s = sum(x["sol"] for x in sb if not x["buy"]) + f_sol
            held = max(s_tok_b - s_tok_s, 1)
            fb = next((x for x in sb if x["buy"]), None)
            big_before = [x for x in tr[st["g_end"]:kv] if (not x["buy"]) and x["sol"] >= MIN_SELL]
            def pr(x): return x["vsol"] / x["vtok"]
            j5 = next((j for j in range(kv - 1, -1, -1) if t["s"] - tr[j]["s"] >= 5), None); j20 = next((j for j in range(kv - 1, -1, -1) if t["s"] - tr[j]["s"] >= 20), None)
            p_pre = p_before
            w3 = [x for x in tr[max(0, kv - 30):kv] if t["s"] - x["s"] <= 3]
            insb = sum(x["tok"] for x in tr[:kv] if x["user"] in st["insiders"] and x["buy"]); inss = sum(x["tok"] for x in tr[:kv] if x["user"] in st["insiders"] and not x["buy"])
            xf = dict(s_frac=round(min(t["tok"] / held, 2.0), 3), s_pnl=round((s_sol_s - s_sol_b) / 1e9, 3), s_nb=sum(1 for x in sb if x["buy"]),
                      s_entry=(fb["s"] - S) if fb else -1, s_in_bundle=int(su in st["insiders"]), n_big=len(big_before),
                      since_big=(t["s"] - big_before[-1]["s"]) if big_before else 999, ret5=round(p_pre / pr(tr[j5]), 4) if j5 is not None else 1.0,
                      ret20=round(p_pre / pr(tr[j20]), 4) if j20 is not None else 1.0, peak_mult=round(peak / pbp, 4), b3=round(sum(x["sol"] for x in w3 if x["buy"]) / 1e9, 3),
                      nb3=sum(1 for x in w3 if x["buy"]), sellers20=len({x["user"] for x in w20 if not x["buy"]}), uniq_buyers=len({x["user"] for x in tr[:kv] if x["buy"]}),
                      ins_sold=round(inss / insb, 3) if insb else 0.0, net_flow=round((sum(x["sol"] for x in tr[:kv] if x["buy"]) - sum(x["sol"] for x in tr[:kv] if not x["buy"])) / 1e9, 3))
            if COH:
                adj = t["tok"] if t["user"] in COH else 0
                xf.update(coh_n=len(cbS), coh_20=len({x["user"] for x in w20 if x["buy"] and x["user"] in COH}), coh_seller=int(t["user"] in COH),
                          coh_sol=round(csol / 1e9, 3), coh_held=sum(1 for u in cbS if cbal[u] - (adj if u == t["user"] else 0) > 0))
            xf["slotpos"] = round(t["i"] / max(SS.get(t["s"], 400), t["i"] + 1), 3)       # the sell's position in its block (0..1)
            row = dict(m=m, run=run, bt=c["bt"], age=round(age, 2), sell=round(f_sol / 1e9, 3), seller=t["user"][:8], ins=t["user"] in st["insiders"], xf=xf,
                       drop=round(p_after / p_before, 4), vsol=round(f_vsol / 1e9, 2), nb=sum(1 for x in tr[:kv] if x["buy"]), ns=sum(1 for x in tr[:kv] if not x["buy"]),
                       pb=round(p_after / pbp, 4), dd=round(p_after / peak, 4), b20=round(sum(x["sol"] for x in w20 if x["buy"]) / 1e9, 3),
                       s20=round(sum(x["sol"] for x in w20 if not x["buy"]) / 1e9, 3), u20=len({x["user"] for x in w20 if x["buy"]}),
                       dev=round(sum(x["sol"] for x in tr[:st["g_end"]] if x["buy"]) / 1e9, 3), glued=len(st["glued"]),
                       first_big=not any((not x["buy"]) and x["sol"] >= MIN_SELL for x in tr[st["g_end"]:kv]), pnl={}, ahead={}, px={}, kv_lag=k - kv)
            for Lm in LATS:
                ke = k + 1
                if Lm == 999:                                   # "first in the next slot": after every trade of the sell's slot
                    while ke < len(tr) and tr[ke]["s"] <= t["s"]: ke += 1
                else:
                    while ke < len(tr) and arr(tr[ke]) < a0 + Lm: ke += 1
                if ke >= len(tr): continue
                row["ahead"][str(Lm)] = ke - k - 1
                row["px"][str(Lm)] = round((tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after, 4)
                s_land = (t["s"] + 1) if Lm == 999 else int((a0 + Lm) // SMS)
                row["pnl"][str(Lm)] = {str(H): round(rt_fixed(tr, ke, fr, H, s_land), 5) for H in HSET}
                row.setdefault("xg", {})[str(Lm)] = exit_grid(*rt_path(tr, ke, fr, s_land))
                for tp, hc in TPS: row["pnl"][str(Lm)][f"tp{tp:g}c{int(hc)}"] = round(rt_tp2(tr, ke, fr, tp, int(hc), s_land), 5)
                for xs, dd, hm in EVX: row["pnl"][str(Lm)][f"ev{xs:g}_{dd:g}_{int(hm)}"] = round(rt_ev(tr, ke, fr, xs, dd, int(hm), s_land), 5)
                for dl, hm in FOLX: row["pnl"][str(Lm)][f"fol{int(dl)}_{int(hm)}"] = round(rt_follow(tr, k, ke, fr, dl, int(hm), s_land), 5)
                for tp, sl, hm in TPSL: row["pnl"][str(Lm)][f"ts{tp:g}_{sl:g}_{int(hm)}"] = round(rt_tpsl(tr, ke, fr, tp, sl, int(hm), s_land), 5)
            lab = {}
            for x in tr[k + 1:k + 600]:
                if arr(x) > a0 + 1000 or ((not x["buy"]) and x["sol"] >= MIN_SELL): break      # credit a buy to the latest dump before it
                if x["buy"] and x["user"] in TARGETS and x["user"][:8] not in lab: lab[x["user"][:8]] = round(arr(x) - a0, 1)
            row["lab"] = lab
            pbig = [x for x in tr[:k] if (not x["buy"]) and x["sol"] >= MIN_SELL]
            row["prev_sell_ms"] = round(a0 - arr(pbig[-1]), 1) if pbig else -1
            lb = next((x for x in reversed(tr[:k]) if x["buy"]), None)
            row["tok"] = dict(creator=(c.get("creator") or "")[:8], n_tr=k, vmax=round(max(x["vsol"] for x in tr[:k + 1]) / 1e9, 2),
                              since_buy=round((a0 - arr(lb)) / 1000, 3) if lb else -1, cidx=c.get("idx"))
            out.append(row); busy = t["s"] + int(os.environ.get("DIP_BUSY", "20"))
    return out, hk
if __name__ == "__main__":
    res = []; HKD = []
    with Pool(8) as p:
        for o, h in p.imap_unordered(work, sorted(byb), chunksize=2): res += o; HKD += h
    LG = [int(x) for x in LATS]; XG = np.full((len(res), len(LG), len(GRID)), np.nan, np.float32)
    with gzip.open(os.environ.get("DIP_OUT", "/home/moiz/sniper/ops/overnight/sel/sel3_events.jsonl.gz"), "wt") as f:
        for i, r in enumerate(res):
            for j, Lm in enumerate(LG):
                if str(Lm) in r.get("xg", {}): XG[i, j] = r["xg"][str(Lm)]
            r.pop("xg", None); f.write(json.dumps(r) + "\n")
    np.save(os.environ.get("DIP_XOUT", "/home/moiz/sniper/ops/overnight/sel/sel3_exits.npy"), XG)
    json.dump({"lats": LG, "grid": GRID}, open("/home/moiz/sniper/ops/overnight/sel/sel3_exits_grid.json", "w"))
    print("events", len(res))
    if HKD:
        HKD.sort(); n = len(HKD)
        print(f"HkQ7hMjy buys right after a big sell: {n}; proxy delay after the sell (ms): p10 {HKD[n // 10]} p25 {HKD[n // 4]} median {HKD[n // 2]} p75 {HKD[3 * n // 4]} p90 {HKD[9 * n // 10]}")
    for Lm in LATS:
        v = [r["pnl"][str(Lm)][str(HSET[0])] for r in res if str(Lm) in r["pnl"]]; a = [r["ahead"][str(Lm)] for r in res if str(Lm) in r["ahead"]]
        print(f"  L={Lm:3d} ms: n {len(v)} mean(first exit) {statistics.mean(v):+.4f} | trades ahead of us: median {statistics.median(a)} mean {statistics.mean(a):.2f}")

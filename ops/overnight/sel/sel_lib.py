#!/usr/bin/env python3
# Shared loader for the selection study with TP / SL / time-limit exits (local only): events (sel2_events.jsonl.gz), the exit
# grid (sel2_exits.npy: events x entry delay 35/50/75 ms x exit), features (dump-time only) incl. the three wallets' earlier dip
# buys on the token, labels, train/test split by PKT time, and P&L per exit with the 2% entry guard (no fill -> -0.0002).
import json, gzip, os, time, calendar
import numpy as np
D = "/home/moiz/sniper/ops/overnight/sel"; VER = os.environ.get("SELV", "2")
EV = [json.loads(l) for l in gzip.open(f"{D}/sel{VER}_events.jsonl.gz", "rt")]
XG = np.load(f"{D}/sel{VER}_exits.npy", mmap_mode="r"); _g = json.load(open(f"{D}/sel{VER}_exits_grid.json"))
LATS = _g["lats"]; GRID = [tuple(x) for x in _g["grid"]]
FEATS = ["age", "sell", "drop_pct", "vsol", "pb", "dd", "nb", "ns", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "s_frac", "s_pnl", "s_nb",
         "s_entry", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow", "slotpos",
         "prev_sell_ms", "n_tr", "vmax", "since_buy", "tgt_n", "tgt_since"]
if "coh_n" in EV[0]["xf"]: FEATS += ["coh_n", "coh_20", "coh_seller", "coh_sol", "coh_held"]
order = sorted(range(len(EV)), key=lambda i: (EV[i]["m"], EV[i]["age"])); _pm = None; _b = []
for i in order:                                   # the three wallets' earlier dip buys on this token (only buys before this dump)
    r = EV[i]
    if r["m"] != _pm: _pm = r["m"]; _b = []
    t0 = r["age"] * 1000.0; past = [b for b in _b if b < t0]
    r["tgt_n"] = len(past); r["tgt_since"] = (t0 - max(past)) / 1000.0 if past else 1e9
    for w, d in r["lab"].items(): _b.append(t0 + d)
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
X = np.array([[fv(r, k) for k in FEATS] for r in EV], dtype=float)
T = np.array([r["bt"] + r["age"] for r in EV]); M = np.array([r["m"] for r in EV]); AGE = np.array([r["age"] for r in EV])
FILL = np.array([[str(L) in r["px"] and r["px"][str(L)] <= 1.02 for L in LATS] for r in EV])
HAS = ~np.isnan(np.asarray(XG[:, :, 0]))
LAB = {w: np.array([w in r["lab"] for r in EV]) for w in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX")}
LAB["ANY"] = LAB["HkQ7hMjy"] | LAB["DYXDDrZC"] | LAB["haqqiUUX"]
def pkt(s): return calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
SPLIT = pkt(os.environ.get("SPLIT", "10-23 06:00")); TR = T < SPLIT; TE = ~TR
def hours(m): return (T[m].max() - T[m].min()) / 3600 if m.any() else 1.0
HTR, HTE = hours(TR), hours(TE)
def pnl(L, e):
    """P&L per event at entry delay L (35/50/75) with exit index e: grid value if the guard passes, else a failed attempt."""
    j = LATS.index(L); v = np.where(FILL[:, j], np.asarray(XG[:, j, e]), -0.0002)
    return np.where(HAS[:, j], v, 0.0)
def ename(e):
    g = GRID[e]
    if g[0] == "H": return f"sell after {g[1]} slots"
    tp, sl, cap, mh = g[1:]
    return (f"TP +{tp:.0%}" if tp < 5 else "no TP") + " / " + (f"SL -{sl:.0%}" if sl < 5 else "no SL") + f" / time limit {cap} slots ({cap * 0.212:.1f} s)" + (f" / min hold {mh}" if mh > 1 else "")
def spaced(mask, gap_s=5 * 0.212):
    """our picks: no new pick on a token within gap_s seconds of our previous pick on it"""
    idx = np.where(mask)[0]; idx = idx[np.lexsort((AGE[idx], M[idx]))]; keep = np.zeros(len(EV), bool); last = {}
    for i in idx:
        if M[i] in last and AGE[i] - last[M[i]] < gap_s: continue
        last[M[i]] = AGE[i]; keep[i] = True
    return keep
def summary(mask, part, e, hrs):
    mm = mask & part; o = {"n": int(mm.sum()), "ph": mm.sum() / hrs}
    for L in LATS:
        p = pnl(L, e); j = LATS.index(L); fl = mm & FILL[:, j] & HAS[:, j]
        o[L] = (float(p[mm].sum()), int(fl.sum()), float((p[fl] > 0).mean()) if fl.any() else 0.0)
    return o
def fmt(o):
    return f"{o['n']:5d} picks ({o['ph']:5.1f}/h) | " + " | ".join(f"{L} ms {o[L][0]:+7.2f} fills {o[L][1]:4d} win {o[L][2]:.0%}" for L in LATS)

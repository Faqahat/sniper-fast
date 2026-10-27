#!/usr/bin/env python3
# Shared loader + engine replay for the dipdetect study (read-only). Data = dd1_<day>.npz (dd1_build.py).
# Engine limits as the live bot / the baseline replays (sel/dayexit_fast_sum.py): one open position per server; a server trades
# only dumps in its near-leader slots (FRA list -> Frankfurt, AMS list -> Amsterdam); busy until our sell lands + 0.3 s after a
# fill, 0.8 s after a blocked (guard) buy; 5 slots between picks on the same token; fixed cost FIX per filled round trip (on top of
# the pump fees inside the replay), FAIL per blocked buy.
import json, time, calendar
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/dipdetect"
FIX = 0.0051          # = replay tx model 0.0016 + 0.0035 "real costs" of the baseline replays (measured live ~0.0043)
FAIL = 0.0005
SMS = 212.0
pk = lambda s: calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
# evaluation windows (PKT) = where the IMIT1 score is known for every in-envelope dump (baseline fully defined)
WIN = {"R1": ("10-22 03:07", "10-22 18:05"), "R2": ("10-22 20:43", "10-23 18:19"), "R3": ("10-23 19:26", "10-24 16:27"),
       "R4": ("10-24 19:25", "10-24 22:41")}
IMIT_TRAIN_END = pk("10-23 06:00")     # IMIT1 was fit on dumps before this (R1 + R2 until 06:00 are in-sample for IMIT1)
M = json.load(open(f"{OUT}/dd1_meta.json"))
EXN = M["exits"]; EXI = {k: i for i, k in enumerate(EXN)}
FEATS = M["feats"]; XF = M["xf"]
FN = FEATS + XF + ["f1"]
FNI = {k: i for i, k in enumerate(FN)}
THR = {"top2": 0.5419185740413283, "top4": 0.21088520504965255, "top8": -0.18683692105426744}
E_13 = EXI["c6_tpnone_sl10"]; E_4S = EXI["c19_tpnone_sl20"]

def load(day, window=True):
    z = np.load(f"{OUT}/dd1_{day}.npz"); d = {k: z[k] for k in z.files}
    # block time of the dump: bt is 0 for some rows -> fall back to the slot clock anchored on rows that have both
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any():
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1); bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    d["t"] = bt
    if window:
        a, b = WIN[day]; m = (d["t"] >= pk(a)) & (d["t"] < pk(b))
        d = {k: v[m] for k, v in d.items()}
    d["day"] = day
    d["Xall"] = np.concatenate([d["F"], d["X"], d["f1"][:, None]], 1).astype(np.float32)
    X = d["Xall"]; f = lambda k: X[:, FNI[k]]
    d["env"] = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    d["hour"] = ((d["t"] + 5 * 3600) // 3600) % 24
    o = np.argsort(d["arr"], kind="stable"); d["order"] = o
    return d

def feat(d, k): return d["Xall"][:, FNI[k]]

def sim(d, sel, lat=0, ex=E_13, servers=("f", "a"), fix=FIX, fail=FAIL, spacing=5, margin=300.0, fail_busy=800.0, scale=None, detail=False):
    """greedy engine replay. sel: bool mask over rows (picked if True). ex: exit index (int) or per-row int array.
    scale: optional per-row multiplier of the P&L (size proxy; fixed costs unchanged). Returns totals over the servers."""
    out = dict(att=0, fill=0, fail=0, pnl=0.0, win=0, rows=[])
    exa = np.broadcast_to(np.asarray(ex), sel.shape)
    for sv in servers:
        near = d["near_f"] if sv == "f" else d["near_a"]
        idx = d["order"][(sel & near)[d["order"]]]
        busy = -1e18; last = {}
        for r in idx.tolist():
            a = d["arr"][r]
            if a < busy: continue
            st = d["st"][r, lat]
            if st == 2: continue
            t = d["tok"][r]; s = d["s"][r]
            if t in last and s < last[t] + spacing: continue
            last[t] = s; out["att"] += 1
            if st == 1:
                out["fail"] += 1; out["pnl"] -= fail; busy = a + fail_busy
                if detail: out["rows"].append((r, sv, -fail, 0))
                continue
            e = int(exa[r]); p = float(d["pnl"][r, lat, e]) * (scale[r] if scale is not None else 1.0) - fix
            out["fill"] += 1; out["pnl"] += p; out["win"] += p > 0
            busy = (d["sin"][r, lat] + d["off"][r, lat, e]) * SMS + 75.0 + margin
            if detail: out["rows"].append((r, sv, p, 1))
    n = out["fill"]
    out["per_fill"] = out["pnl"] / n if n else 0.0
    out["fill_rate"] = n / out["att"] if out["att"] else 0.0
    out["winr"] = out["win"] / n if n else 0.0
    return out

def hours(d):
    return (d["t"].max() - d["t"].min()) / 3600.0

def fmt(o, h=None):
    s = f"{o['pnl']:+7.2f} SOL  fills {o['fill']:4d}/{o['att']:4d} ({100 * o['fill_rate']:3.0f}%)  {o['per_fill']:+.4f}/fill  win {100 * o['winr']:3.0f}%"
    if h: s += f"  ({o['pnl'] / h * 24:+.2f}/24h)"
    return s

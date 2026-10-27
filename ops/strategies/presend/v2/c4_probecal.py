#!/usr/bin/env python3
# PRE-SEND V2 step c4: CALIBRATION TABLE = the live probe (AMS r16, 10-25 08:49-09:49 PKT, 118 armed windows, 0.2 SOL,
# 3.79 attempts per armed slot, drop 12%, exit 2 slots / TP 10% / SL 20%) vs the V2 replay of the SAME 118 windows on the
# full R4 tape, per landing row (study c = +10 ms, study r4 = U(0,53), calibrated P = 3.79 / slot, L4, L8).
# Each live window is replayed on its own (the live arming / blocking already happened). Read-only.
# Compared: fills (and per-window agreement), landing after the crossing, P&L after pump fees before tx costs (live: realized +
# the fill's fixed tx costs; replay: path P&L at 0.2 SOL), failed attempts.
# usage (probe 1, default): python3 c4_probecal.py
#        (a later probe): python3 c4_probecal.py --jsonl dip_ams_rN.jsonl --day R5 --size 0.55 --rows c,L8,L8x --out c4_probe2
#        (--day = a v2data tape key whose v2_<day>.npz covers the probe: r5_fresh.sh RUN FROM builds "R5")
import sys, os, json, collections, argparse
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
import v2eng as E
ap = argparse.ArgumentParser()
ap.add_argument("--jsonl", default="/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"); ap.add_argument("--day", default="R4")
ap.add_argument("--size", type=float, default=0.2); ap.add_argument("--rows", default="c,r4,P,L4,L4x,L8,L8x,L20")
ap.add_argument("--W", type=int, default=10); ap.add_argument("--ex", default="c2_tp10_sl20"); ap.add_argument("--y", type=float, default=0.12)
ap.add_argument("--out", default="c4_probecal")
A = ap.parse_args()
F = A.jsonl
OUT = f"{V.OUT}/{A.out}"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
FIX = E.COST["real"]["fill"]
arms = {}; fills = {}; real = {}; close = {}; land = {}; att = collections.Counter(); dis = {}; sellfee = {}
for l in open(F):
    if '"presend_' not in l: continue
    o = json.loads(l); ev = o["ev"]
    if ev == "presend_live_arm": arms[o["w"]] = o
    elif ev == "presend_live_fill": fills[o["w"]] = o
    elif ev == "presend_live_realized": real[o["w"]] = o
    elif ev == "presend_live_close": close[o["w"]] = o
    elif ev == "presend_attempt_land": land[o["sig"]] = o
    elif ev == "presend_attempt": att[o["w"]] += 1
    elif ev == "presend_live_disarm": dis[o["w"]] = o
    elif ev == "presend_live_sell_land": sellfee[o["w"]] = sellfee.get(o["w"], 0) + (o.get("fee") or 0)
D = E.load(A.day)
tp = V.load_day(A.day, cols=("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok"))
M = tp["meta"]; mint_tok = {x["m"]: t for t, x in enumerate(M)}
# tape row of each live trigger -> T2 window id
key = {}
for w, a in arms.items():
    tr = a["trig"]; t = mint_tok.get(tr["mint"])
    if t is None: continue
    o = int(tp["off"][t]); n = int(tp["cnt"][t]); sl = slice(o, o + n)
    rr = np.flatnonzero((tp["s"][sl] == tr["slot"]) & (tp["i"][sl] == tr["idx"]) & (tp["tokn"][sl] == tr["tok"]))
    if len(rr): key[w] = o + int(rr[0])
wj = {int(j): q for q, j in enumerate(D["w_j"].tolist()) if D["w_fam"][q] == 0}
mapped = {w: wj[j] for w, j in key.items() if j in wj}
say(f"probe windows {len(arms)}: trigger found on the tape {len(key)}, mapped to a replay T2 window {len(mapped)}")
yi = E.YS.index(A.y); si = E.SIZES.index(A.size); e = E.EXI[A.ex]
live_f = {w for w in mapped if w in fills}
def txcost(w):
    """the fill's own tx costs from the records (buy fee + tip, sell fees + tips); probe 1: = 2,010,120 lamports each"""
    f = fills[w]; c = close.get(w, {})
    st = sum(x[2] for x in (c.get("sell_sigs") or []) if len(x) > 2 and x[1])
    return ((f.get("fee") or 0) + (f.get("tip") or 0) + sellfee.get(w, 0) + st) * 1e-9
live_pnl = {w: (real[w]["pnl"] * 1e-9 + txcost(w)) for w in live_f if w in real}      # after pump fees, before tx costs
live_D = {}
for w in live_f:
    l = land.get(fills[w]["sig"])
    if l: live_D[w] = l.get("ms_after_x_a")
say(f"LIVE on the mapped windows: fills {len(live_f)}, P&L after pump fees before tx costs {sum(live_pnl.values()):+.4f} SOL "
    f"({sum(live_pnl.values()) / max(len(live_pnl), 1):+.5f}/fill), landing after the crossing p50 {np.median(list(live_D.values())):.1f} ms")
TAB = {}
for row in A.rows.split(","):
    ri = E.RN.index(row); cal = E.ROWS[ri][1] in ("dl1", "dl2", "dl1x")
    rf = {}; pn = {}; Dd = {}
    for w, q in mapped.items():
        f = D["FR"][yi, ri, q]
        if f < 0: continue
        st = D["w_start"][q]; en = min(D["w_end"][q], st + A.W * 212.0)
        ok = (D["f_xa"][f] < en) if cal else (D["f_land"][f] < en)
        if not ok: continue
        p = D["f_pid"][f]; rf[w] = f; pn[w] = float(D["p_pnl"][p, si, e]); Dd[w] = float(D["f_f"][f, E.FFI["D"]])
    agree = collections.Counter(("live fill" if w in live_f else "live none") + " / " + ("replay fill" if w in rf else "replay none") for w in mapped)
    both = [w for w in rf if w in live_f]
    TAB[row] = dict(fills=len(rf), pnl=sum(pn.values()), per_fill=sum(pn.values()) / max(len(pn), 1), D50=float(np.median(list(Dd.values()))) if Dd else None,
                    agree=dict(agree), both_live=sum(live_pnl.get(w, 0) for w in both), both_replay=sum(pn[w] for w in both))
    say(f"  row {row:3s}: fills {len(rf):3d} | P&L after pump fees {sum(pn.values()):+.4f} ({TAB[row]['per_fill']:+.5f}/fill) | D p50 {TAB[row]['D50']} | {dict(agree)} | "
        f"on windows both filled: live {TAB[row]['both_live']:+.4f} replay {TAB[row]['both_replay']:+.4f} ({len(both)})")
# failed attempts: live vs model (k x armed slots)
la = sum(att[w] for w in mapped)
say(f"attempts on the mapped windows: live {la} ({la / max(len(live_f), 1):.0f} per fill)")
json.dump(dict(tab=TAB, live=dict(fills=len(live_f), pnl=sum(live_pnl.values()), D=list(live_D.values()), attempts=la)), open(OUT + ".json", "w"), default=float)
open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")

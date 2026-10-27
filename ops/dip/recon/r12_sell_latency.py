#!/usr/bin/env python3
# r12: how our real SELLS land. Time-limit: slot offset vs entry and index inside the slot. Stop-loss: the trade that pushed
# our position value to the stop (real tape, real tokens) -> where our sell landed (block-position ms after that trade).
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
P = json.load(open(f"{R.WORK}/pertrade.json"))
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
F = {(r["srv"], r["run"]): r["cfg"] for r in json.load(open(f"{R.WORK}/fires.json"))["runs"]}
sl_lat = []; rows = []
for o in P:
    if not o["live_fill"] or o.get("sell_slot") is None: continue
    cfg = F[(o["srv"], o["run"])]; sl = cfg["sl"]
    TP = TPS[o["tape"]]; t = TP.mint2t[o["mint"]]; tp = TP.token(t)
    # our buy row in the real tape
    jb = [x for x in range(tp["n"]) if tp["ours"][x] and tp["buy"][x] and tp["s"][x] == o["land_slot"] and tp["i"][x] == o["land_idx"]]
    if not jb: continue
    jb = jb[0]; q = float(tp["tokn"][jb]); key_sell = o["sell_slot"] * 100000 + o["sell_idx"]
    trig = None
    for x in range(jb + 1, tp["n"]):
        if tp["SI"][x] >= key_sell: break
        if tp["ours"][x]: continue
        V = float(tp["vsol"][x]); T = float(tp["vtok"][x]); fr = float(tp["fr"][x])
        val = V * q / (T + q) * (1 - fr) / 1e9 / o["size"]
        if val <= 1 - sl and trig is None: trig = (x, val)
    a_sell = R.arrival(o["sell_slot"], o["sell_idx"])
    if o.get("exit_why_live") == "stop-loss" and trig is not None:
        x, val = trig; L = a_sell - float(tp["arr"][x])
        sl_lat.append(L); rows.append((o["srv"], o["run"], o["mint"][:6], round(val, 3), int(tp["s"][x]), int(tp["i"][x]), o["sell_slot"], o["sell_idx"], round(L, 1)))
print("stop-loss sells: block-position ms from the trigger trade to our sell landing:")
for r in rows: print("  ", r)
if sl_lat:
    a = np.array(sl_lat); print(f"  n {len(a)}, p25 {np.percentile(a, 25):.0f}, median {np.median(a):.0f}, p75 {np.percentile(a, 75):.0f}, mean {a.mean():.0f}")
json.dump(dict(sl_lat=sl_lat), open(f"{R.WORK}/sell_latency.json", "w"))

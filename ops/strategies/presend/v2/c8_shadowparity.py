#!/usr/bin/env python3
# PRE-SEND V2 step c8: the engine's own pre-send SHADOW (paper, same code, FRA r15 local copy / AMS r14 / AMS r16) vs this replay's
# study row c on the same span: windows, fills and gross P&L (0.55 SOL, c2_tp10_sl20; create-slot triggers excluded on both sides).
import sys, os, json, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
FILES = ["/home/moiz/sniper-data/recon/live/dip_r15.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r14.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"]
D = E.load("R4")
m = R.fmask(D, dict(fam="T2"))
for f in FILES:
    arms = {}; fills = {}; exits = {}; ts = []
    for l in open(f):
        if '"presend_' not in l: continue
        o = json.loads(l); ev = o["ev"]
        if ev == "presend_arm": arms[o["w"]] = o; ts.append(o["t"] / 1e9)
        elif ev == "presend_fill" and o["row"] == "c": fills[o["w"]] = o
        elif ev == "presend_exit" and o["row"] == "c": exits[o["w"]] = o
    if not ts: continue
    t0, t1 = min(ts), max(ts)
    ok = [w for w, a in arms.items() if a.get("age_slots", 1) != 0 and a["rows"]["c"] == "armed"]
    sf = [w for w in ok if w in fills and w in exits]
    sp = sum(exits[w]["pnl"] for w in sf)
    tm = (D["w_t"] >= t0) & (D["w_t"] < t1 - 60)
    o = E.run(D, m & tm, 10, 0.12, "c", 0.55, "c2_tp10_sl20", servers=2, cost="study")
    print(f"{os.path.basename(f)} {V.pkt(t0)} -> {V.pkt(t1)}: SHADOW row c armed {len(ok)}, fills {len(sf)}, gross {sp:+.3f} SOL | REPLAY row c armed {o['armed']}, fills {o['fill']}, gross {o['gross']:+.3f} SOL")

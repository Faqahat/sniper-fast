#!/usr/bin/env python3
"""BOTS step 12 (read-only): how much of 247's / 248's dump lots (and P&L) does our current engine already take? Only lots bought while one
of our live runs was on (g0_runs windows, either server). Ours = a regular (M2) fire on the same dump (fires_tape), or a pre-send fill
on the same mint within 2 slots of his buy (live_presend landed fills). MEASURED.
Out: bots/b12.txt"""
import json, pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import Out
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
P = Out(f"{OUT}/b12.txt")
rows = pickle.load(open(f"{OUT}/b1.pkl", "rb"))
G = json.load(open("/home/moiz/sniper-data/haqq_dissect/gap/g0_runs.json"))
win = sorted((v["start"], v["end"]) for v in G.values())
F = pickle.load(open("/home/moiz/sniper-data/dv8/fires_tape.pkl", "rb"))
fires = {(f["mint"], f["ds"], f["di"]): f for f in F}
PS = pickle.load(open("/home/moiz/sniper-data/dv8/live_presend.pkl", "rb"))
psf = collections.defaultdict(list)
for p in PS:
    if p.get("landed") and not p.get("dry") and p.get("pos"): psf[p["mint"]].append(p["pos"][0])
def live(t): return any(a <= t <= b for a, b in win)
P("# Overlap of our live engine with bots 247 / 248 (dump-reactive lots in the dv8 universe, bought while a run of ours was live; MEASURED)")
P("| bot | lots while live | his net | we fired a regular (M2) buy on the same dump | we FILLED | his net on our fires | his net on our fills | our pre-send landed on the mint within 2 slots | his net there |")
P("|---|---|---|---|---|---|---|---|---|")
for c in (247, 248):
    v = [r for r in rows if r["code"] == c and r["usable"] and not r["gap"] and r["dump"] and r["u"] is not None and live(r["bt"])]
    fi = [r for r in v if (r["mint"], r["d_slot"], r["d_idx"]) in fires]
    fl = [r for r in fi if fires[(r["mint"], r["d_slot"], r["d_idx"])]["out"] == "fill"]
    ps = [r for r in v if any(abs(s - r["slot"]) <= 2 for s in psf.get(r["mint"], []))]
    P(f"| {c} | {len(v):,} | {sum(r['net'] for r in v):+.2f} | {len(fi)} ({100 * len(fi) / max(len(v), 1):.1f}%) | {len(fl)} ({100 * len(fl) / max(len(v), 1):.1f}%) | "
      f"{sum(r['net'] for r in fi):+.2f} | {sum(r['net'] for r in fl):+.2f} | {len(ps)} ({100 * len(ps) / max(len(v), 1):.1f}%) | {sum(r['net'] for r in ps):+.2f} |")
tot_live = sum(b - a for a, b in win) / 3600
P(f"- run windows total {tot_live:.0f} h (both servers, overlapping windows counted twice)")
P.save()

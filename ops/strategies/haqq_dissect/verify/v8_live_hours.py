#!/usr/bin/env python3
"""VERIFY v8 (MEASURED live vs INFERRED replay): our LIVE pre-send (FRA r26 + r27) per fresh PKT hour - fills, wallet-realized P&L
(presend_live_realized, all tx costs) minus failed-try fees - next to G2's rsim BASE replay (today's T2 pre-send, 0.40 SOL) on the
same fresh tape, mean over draws. usage: v8_live_hours.py RSIMPKL"""
import sys, json, pickle, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import v1b_report as B
DATA = "/home/moiz/sniper-data/haqq_dissect/verify"; FRESH0 = 1793131823
def hr(t): return (int(t) + 18000) // 3600 * 3600 - 18000
H = collections.defaultdict(lambda: collections.defaultdict(float)); fill_t = {}
BTE = int(np.load(f"{DATA}/tab/slots.npy")["bt"].max()) - 90
for rn, fn in (("r26", "/home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl"), ("r27", f"{DATA}/live/dip_r27.jsonl")):
    for l in open(fn, errors="ignore"):
        if '"presend_' not in l: continue
        try: r = json.loads(l)
        except Exception: continue
        ev = r.get("ev")
        if ev == "presend_live_fill": fill_t[(rn, r["mint"])] = r["t"] / 1e9
        elif ev == "presend_attempt_land" and r.get("res") != "ok" and FRESH0 < (r.get("first_rx") or 0) / 1e9 < BTE:
            H[hr(r["first_rx"] / 1e9)]["fees"] += r.get("fee", 5120) / 1e9
        elif ev == "presend_live_realized":
            t = fill_t.get((rn, r["mint"]))
            if t and FRESH0 < t < BTE: H[hr(t)]["pnl"] += r["pnl"] / 1e9; H[hr(t)]["fills"] += 1
Z = pickle.load(open(sys.argv[1], "rb")); sl, bt = Z["smap_slots"]; sl = sl.astype(np.int64); bt = bt.astype(np.int64)
s2b = lambda s: int(bt[min(max(int(np.searchsorted(sl, s)), 0), len(sl) - 1)])
nd = len(Z["out"]["base"]); RB = collections.defaultdict(lambda: np.zeros(2))
for d in range(nd):
    for h, a in B.agg(Z["out"]["base"][d], s2b).items(): RB[h] += np.array([a[0], (a[1] - a[2]) / 1e9]) / nd
print("| Hour (PKT, after 01:10) | Live fills | Live net SOL (realized - failed fees) | Replay base fills | Replay base model net | Live / replay |")
print("|---|---|---|---|---|---|")
tl = tr = 0
for h in sorted(Z["hours"]):
    v = H.get(h, {}); ln = v.get("pnl", 0) - v.get("fees", 0); rb = RB.get(h, np.zeros(2))
    tl += ln; tr += rb[1]
    print(f"| {time.strftime('%m-%d %H:%M', time.gmtime(h + 18000))} | {v.get('fills', 0):.0f} | {ln:+.3f} | {rb[0]:.0f} | {rb[1]:+.3f} | {ln / rb[1] if rb[1] else float('nan'):.2f} |")
print(f"| Total | | {tl:+.3f} | | {tr:+.3f} | {tl / tr:.2f} |")
print("live = 0.45 SOL size, with the QUIET skip; replay = 0.40 SOL, no QUIET skip. Live hours after the tape end are not in the replay.")

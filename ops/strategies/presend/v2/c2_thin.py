#!/usr/bin/env python3
# PRE-SEND V2 step c2: how the landing after a dump scales with the attempt rate, MEASURED by thinning the probe's real attempt
# stream (AMS r16): keep every m-th attempt of each window (all m phases averaged) -> k = 3.79 / m per armed slot, and recompute,
# for every >= 2% one-trade dump inside an armed window, the first attempt landing after it that could fill:
#   signed before we first saw the dump (server clock) AND not a deadline failure (landing slot <= its deadline).
# D = its landing - the dump on the block clock (the replay's clock). Also the share of dumps with no such attempt.
# Then fits D ~ U(0, g) * s + e (g = 212 / k) per quantile to see if the bulk scales with the attempt gap.
# -> /home/moiz/sniper-data/presend_v2/c2_thin.json (+ .txt)
import sys, json, collections
import numpy as np
F = sys.argv[1] if len(sys.argv) > 1 else "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"
OUT = "/home/moiz/sniper-data/presend_v2/c2_thin"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
QS = (10, 25, 50, 75, 90)
def qs(v): return [float(np.percentile(v, p)) for p in QS] if len(v) else [None] * len(QS)

att = {}; land = {}; dis = {}
for l in open(F):
    if '"presend_' not in l: continue
    o = json.loads(l); ev = o["ev"]
    if ev == "presend_attempt": att[o["sig"]] = o
    elif ev == "presend_attempt_land": land[o["sig"]] = o
    elif ev == "presend_live_disarm": dis[o["w"]] = o
byw = collections.defaultdict(list)
for s, a in att.items():
    l = land.get(s)
    lr = None
    if l and l.get("res") != "unseen" and l.get("a") is not None: lr = l
    byw[a["w"]].append(dict(n=a["n"], ts=a["t"] / 1e6, a=lr["a"] if lr else None, res=lr["res"] if lr else "unseen", slot=lr.get("slot") if lr else None,
                            client=a.get("client") or "?"))
for w in byw: byw[w].sort(key=lambda r: r["n"])
dumps = {}
for l in land.values():
    d = l.get("d")
    if d and d.get("a"): dumps[(l["w"], d["slot"], d["idx"], d.get("j", 0))] = d
say(f"probe {F}: {len(att)} attempts in {len(byw)} windows, {len(dumps)} distinct >= 2% dumps inside armed windows")
res = {}
for m in (1, 2, 3, 4, 6):
    Ds = []; none = 0; tot = 0; big = []; bnone = 0; btot = 0
    for ph in range(m):
        for (w, s, i, j), d in dumps.items():
            X = d["a"]; seen = d.get("first_rx", d["t"]) / 1e6
            A = [r for r in byw[w] if (r["n"] - 1) % m == ph]
            cand = [r for r in A if r["a"] is not None and r["a"] > X and r["ts"] < seen and r["res"] != "deadline"]
            tot += 1; isbig = (d.get("drop_pct") or 0) >= 8; btot += isbig
            if not cand: none += 1; bnone += isbig; continue
            v = min(r["a"] for r in cand) - X; Ds.append(v)
            if isbig: big.append(v)
    k = 3.79 / m
    res[m] = dict(k=k, n=tot, none=none / tot, q=qs(Ds), big_q=qs(big), big_none=bnone / max(btot, 1), D=Ds)
    say(f"  keep 1 of {m} (k {k:4.2f}/slot, gap {212 / k:5.1f} ms): dumps {tot // m}, no attempt could fill {100 * none / tot:4.1f}% | D " +
        " | ".join(f"p{p} {v:6.1f}" for p, v in zip(QS, res[m]["q"])) + f" | ratio to gap: p50 {res[m]['q'][2] / (212 / k):.2f} p25 {res[m]['q'][1] / (212 / k):.2f} p75 {res[m]['q'][3] / (212 / k):.2f}"
        + (f" | dumps >= 8%: p50 {res[m]['big_q'][2]:.1f}, none {100 * res[m]['big_none']:.0f}%" if big else ""))
json.dump(res, open(OUT + ".json", "w"))
open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")

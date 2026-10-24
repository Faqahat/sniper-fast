#!/usr/bin/env python3
# frozen IMIT1 tiers at a 60 ms landing on the TEST hours (never seen), sizes 0.5 / 1 / 2 SOL: per tier the best few exits
# (chosen on TRAIN) and SOL per hour on TEST. Scores come from sel3 (same events), aligned by (mint, age).
import os, sys, json, gzip
os.environ["SELV"] = "3r"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import numpy as np
import sel_lib as S
M = json.load(open("IMIT1.json")); sc = np.load("x4_score_imit1_3r.npy")
cut = np.quantile(S.T[S.TR], 0.8); VA = S.TR & (S.T >= cut) & (sc > -1e8)
thr = dict(M["thresholds"]); thr["top15"] = float(np.quantile(sc[VA], 1 - 0.15))
G = [tuple(g) for g in S.GRID]
for B in ("0.5", "1.0", "2.0"):
    EV = [json.loads(l) for l in gzip.open(f"sel60_b{B}_events.jsonl.gz", "rt")]; XG = np.load(f"sel60_b{B}_exits.npy", mmap_mode="r")
    idx = {(r["m"], r["age"]): i for i, r in enumerate(EV)}; amap = np.array([idx.get((r["m"], r["age"]), -1) for r in S.EV]); ok = amap >= 0
    fill = np.array([r["px"].get("60", 9) <= 1.02 for r in EV])
    print(f"\n=== size {B} SOL, landing 60 ms (TEST {S.HTE:.1f} h)")
    for tier in ("top2", "top4", "top8", "top15"):
        pick = S.spaced(sc >= thr[tier]) & ok
        res = []
        for e, g in enumerate(G):
            v = np.where(fill[amap[pick]], np.nan_to_num(np.asarray(XG[amap[pick], 0, e])), -0.0002)
            tr_m = S.TR[pick]; res.append((v[tr_m].sum(), e, v[~tr_m].sum(), int((~tr_m).sum()), (v[~tr_m] > 0).sum(), int((fill[amap[pick]] & ~tr_m).sum())))
        res.sort(key=lambda x: -x[0])
        _, e, te, n, w, f = res[0]
        print(f"  {tier:5s} exit chosen on TRAIN: {S.ename(e):55s} TEST {n} picks ({n / S.HTE:4.1f}/h), fills {f}, wins {w} -> {te:+6.2f} SOL = {te / S.HTE:+.2f} SOL/h")

#!/usr/bin/env python3
# WALK-FORWARD deployer selection (leak-free): a launch is picked if its deployer's EARLIER launches (outcome known at least
# GAP seconds before this create) averaged >= THR return under the same landing/exit, with >= K past launches.
# History sources: earlier forward-window launches (same sim) + optional pre-window history from the collector table
# (E_bundle_h2s / E_k1_h2s proxies). Reports the picks' PnL per landing config / exit.
import sys, json, gzip, collections, statistics, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
from ana_fwd import rows, NAMES
GAP = 60
def wf(cfg, rule, K=2, THR=0.0, hist_cfg=None, hist_rule=None, case_lists=None):
    i = NAMES.index(rule); hi = NAMES.index(hist_rule or rule); hc = hist_cfg or cfg
    past = collections.defaultdict(list); picks = []
    pend = []                                  # (ready_time, deployer, value)
    for r in rows:
        if hc not in r["cfg"] or cfg not in r["cfg"]: continue
        t = r["bt"] or 0
        while pend and pend[0][0] <= t:
            _, d, v = pend.pop(0); past[d].append(v)
        h = past[r["signer"]]
        if len(h) >= K and statistics.mean(h) >= THR:
            picks.append((r, r["cfg"][cfg]["pnl"][i]))
        pend.append((t + GAP, r["signer"], r["cfg"][hc]["pnl"][hi] / 0.5))
        pend.sort(key=lambda x: x[0])
    return picks
def show(name, picks):
    v = [p for _, p in picks]
    if not v: print(f"   {name}: no picks"); return
    mid = rows[0]["bt"] + (rows[-1]["bt"] - rows[0]["bt"]) / 2
    a = sum(p for r, p in picks if r["bt"] < mid); b = sum(p for r, p in picks if r["bt"] >= mid)
    s = sorted(v)
    print(f"   {name:60} n {len(v):4} total {sum(v):+7.3f} mean {statistics.mean(v):+.4f} win {sum(1 for x in v if x > 0) / len(v):.0%} w/o top2 {sum(s[:-2]):+.3f} halves {a:+.3f}/{b:+.3f}")
for cfg in ("L75", "L60", "L35"):
    print(f"\n== landing {cfg}")
    for rule in ("hold0.3s", "hold1s", "hold2s", "hold5s", "hold10s", "fsell_any", "tp1.15_sl0.8_c20", "tp1.3_slNone_c60", "tp3.0_slNone_c60", "lad_33@1.3_33@1.6_trail"):
        for K, THR in ((2, 0.0), (3, 0.02), (3, 0.05)):
            show(f"{rule} | deployer history K>={K}, mean >= {THR:+.0%}", wf(cfg, rule, K, THR))

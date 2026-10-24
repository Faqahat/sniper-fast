#!/usr/bin/env python3
# "Picker" wallets (profitable even when 1-3 buyers are ahead, longer holds): how they pick and whether their picks pay
# at OUR place. For each wallet's attempted launches (replay window = real place in line; old run = proxy):
#   entry timing (slot offset), deployer concentration, and our outcome on the same launches:
#     G  = S4 mechanics (1% guard, sell at end of next slot)
#     H5 = no guard, buy at our landing, hold ~5 s (25 slots)    H30 = no guard, hold ~30 s
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
AT = collections.defaultdict(dict)
for f in ("attempts_pick.json", "attempts_top8.json", "attempts.json", "attempts_fifaw.json", "attempts_q9z.json", "attempts_ahw.json"):
    for m, v in json.load(open(f)).items(): AT[m].update(v)
WAL = ["2maW7x", "4Yy3xB", "retAum", "FYHggF", "HnFPB3", "6Kj5Ch", "FeCAXC", "A21wCG", "3yrJE1", "5g8bvi"]
todo = [m for m, v in AT.items() if m in L and any(w in v for w in WAL) and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("h5", [(1.0, ("slot", 24))], 7), rp.R("h30", [(1.0, ("slot", 141))], 31)]
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (75,):
            if run == "R2":
                if m not in O: continue
                ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            else: ib, _ = rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015)
            if not o: continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            r = dict(G=(o["eos1"]["pnl"] if ok else -0.005), H5=o["h5"]["pnl"], H30=o["h30"]["pnl"], grad=o["h30"]["grad"])
        if r: out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open("pickers_res.json", "w"))
    print(f"{'wallet':7} {'att':>4} {'fill':>4} | offset: create/next/2-4/5+ | deployers (repeat%) | our outcome on its launches at 75 ms: R2 G / H5 / H30 || R1 G / H5 / H30")
    for w in WAL:
        ms = [m for m, v in AT.items() if w in v and m in L]
        if not ms: continue
        off = collections.Counter(min(AT[m][w][1], 5) if isinstance(AT[m][w], list) and len(AT[m][w]) > 1 else -1 for m in ms)
        fills = sum(1 for m in ms if AT[m][w][0])
        deps = collections.Counter(L[m]["user"] for m in ms); rep = sum(n for n in deps.values() if n >= 2) / len(ms)
        cells = []
        for run in ("R2", "R1"):
            v = [res[m] for m in ms if m in res and L[m]["run"] == run]
            cells.append(" / ".join(f"{sum(x[k] for x in v):+6.2f}" for k in ("G", "H5", "H30")) + f" (n{len(v)})")
        print(f"{w:7} {len(ms):4} {fills:4} | {off.get(0, 0):4}/{off.get(1, 0):4}/{sum(off.get(k, 0) for k in (2, 3, 4)):4}/{off.get(5, 0):4} | {len(deps):4} ({rep:.0%}) | {cells[0]} || {cells[1]}")

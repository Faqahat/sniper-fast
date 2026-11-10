#!/usr/bin/env python3
"""9pQQ sub-strategies: label every closed trip by entry trigger (priority order) and re-entry, exit type and version; P&L tables.
Entry trigger (first match):
  LAUNCH  token age <= 50 slots (~10 s) at its buy
  DIP     another wallet sold >= 0.5 SOL in the 3 slots up to its buy (same slot before it, or 1-3 slots earlier)
  MOMO    others' net buy flow in the 10 slots before >= +1 SOL and the last outside trade was a buy
  DRIFT   everything else (small/quiet flow; last trade a small buy or sell)
Re-entry: k >= 2 (it already round-tripped this mint in the recording).
Exit: TIMER (hold 299-302 s or 599-602 s), else SIGNAL.
Version: V300 (300 s timer era, to 10-31 14:00 PKT) / V600 (after).  Size 0.5 vs 0.7 SOL.
-> clusters.json + printed tables.  usage: a3_clusters.py"""
import pickle, json, collections, time
import numpy as np
import tlib9 as L

V600_FROM = 1793437380            # 10-31 14:03 PKT (first 600 s timer exit), unix

def label(x):
    if x["age"] is not None and x["age"] <= 50: e = "LAUNCH"
    elif (x.get("dump_sol") or 0) >= 0.5: e = "DIP"
    elif x.get("bsol10", 0) - x.get("ssol10", 0) >= 1 and x.get("last_side") == 1: e = "MOMO"
    else: e = "DRIFT"
    hs = x["sbt"] - x["bbt"]
    ex = "TIMER" if hs in (299, 300, 301, 302, 599, 600, 601, 602) else "SIGNAL"
    return e, ("RE" if x["k"] >= 2 else "FIRST"), ex

def stats(v):
    n = np.array([x["net"] for x in v], float) / 1e9
    if not len(n): return {}
    srt = np.sort(n)
    return dict(n=len(v), net=round(n.sum(), 2), msol=round(1000 * n.mean(), 2), win=round(float((n > 0).mean()), 3),
                net_x_top20=round(srt[:-20].sum(), 2) if len(n) > 20 else None, med_msol=round(1000 * float(np.median(n)), 2),
                hold50=int(np.median([x["hold"] for x in v])),
                days={d: round(sum(x["net"] for x in v if L.DAY[x["run"]] == d) / 1e9, 2) for d in L.DAY.values()})

if __name__ == "__main__":
    T = []
    for r in L.RUNS: T += [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x["net"] is not None]
    hrs = {}
    for r in L.RUNS:
        b = [x["bbt"] for x in T if x["run"] == r]; hrs[L.DAY[r]] = (max(b) - min(b)) / 3600
    print("hours per run", {k: round(v, 1) for k, v in hrs.items()})
    out = {}
    def show(name, keyf):
        g = collections.defaultdict(list)
        for x in T: g[keyf(x)].append(x)
        print(f"\n--- {name}")
        print(f"{'group':28s} {'n':>6s} {'net':>8s} {'mSOL':>7s} {'med':>7s} {'win':>5s} {'-top20':>7s} {'hold50':>6s} | per day (net SOL)")
        for k in sorted(g, key=lambda z: -sum(x['net'] for x in g[z])):
            s = stats(g[k]); out[f"{name}|{k}"] = s
            print(f"{str(k):28s} {s['n']:6d} {s['net']:+8.2f} {s['msol']:+7.2f} {s['med_msol']:+7.2f} {s['win']:5.0%} {s['net_x_top20'] if s['net_x_top20'] is not None else 0:+7.2f} {s['hold50']:6d} | "
                  + " ".join(f"{d} {s['days'][d]:+6.1f}" for d in s['days']))
    show("entry", lambda x: label(x)[0])
    show("entry x reentry", lambda x: label(x)[:2])
    show("entry x exit", lambda x: (label(x)[0], label(x)[2]))
    show("exit", lambda x: label(x)[2])
    show("version x size", lambda x: ("V600" if x["bbt"] >= V600_FROM else "V300", round(x["spend"] / 1e9, 1)))
    show("hold band", lambda x: "<6" if x["hold"] < 6 else "6-50" if x["hold"] < 50 else "50-250" if x["hold"] < 250 else "250-1300" if x["hold"] < 1300 else ">=1300")
    show("entry x hold band", lambda x: (label(x)[0], "<50" if x["hold"] < 50 else "50-250" if x["hold"] < 250 else "250-1300" if x["hold"] < 1300 else ">=1300"))
    # concentration
    n = np.sort(np.array([x["net"] for x in T]) / 1e9)
    print("\nall", len(n), "net", round(n.sum(), 2), "top20", round(n[-20:].sum(), 2), "top100", round(n[-100:].sum(), 2), "bottom100", round(n[:100].sum(), 2))
    for r in L.RUNS:
        v = np.sort(np.array([x["net"] for x in T if x["run"] == r]) / 1e9)
        print(L.DAY[r], "n", len(v), "net", round(v.sum(), 2), "/day", round(v.sum() / hrs[L.DAY[r]] * 24, 1), "top20", round(v[-20:].sum(), 2), "w/o top5", round(v[:-5].sum(), 2), "w/o top20", round(v[:-20].sum(), 2))
    json.dump(out, open("/home/it/sniper/ops/strategies/rivals/9pQQ/clusters.json", "w"), indent=1)

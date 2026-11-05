#!/usr/bin/env python3
"""9pQQ re-entries and graduations.  Re-entry: slots since its previous sell on the token, re-entry price vs its previous exit
price, P&L by previous trip result.  Graduation: trips whose sell went through PumpSwap (sold after the curve completed), and the
weight of the top trades.  Read-only.  usage: a4_reentry_grad.py"""
import pickle, json, collections
import numpy as np
import tlib9 as L
out = {}
T = []
for r in L.RUNS: T += [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x["net"] is not None]
own_sell = {}
for r in L.RUNS:
    for x in L.own(r):
        if x["kind"] == "sell": own_sell[x["sig"]] = x
re = [x for x in T if x["k"] >= 2 and x.get("prev_sell_s") is not None]
gap = np.array([x["bs"] - x["prev_sell_s"] for x in re])
out["reentry_gap_slots_p10_25_50_75_90"] = np.percentile(gap, [10, 25, 50, 75, 90]).tolist()
out["reentry_share_of_trips"] = round(len(re) / len(T), 3)
# re-entry price vs previous exit price: use cbal at re-entry vs previous trip's sell curve state (approx via exit_move chain)
byk = collections.defaultdict(list)
prev = {}
for x in sorted(T, key=lambda z: (z["run"], z["mint"], z["k"])):
    key = (x["run"], x["mint"])
    if key in prev and x["k"] >= 2:
        p = prev[key]
        if p.get("cbal") is not None and x.get("cbal") is not None:
            # price at its previous exit ~ price at previous buy * (1+exit_move); now vs then
            pe = L.price(p["cbal"]) * (1 + p.get("exit_move", 0))
            byk["px_vs_prev_exit"].append(L.price(x["cbal"]) / pe - 1)
        byk["prev_win" if p["net"] > 0 else "prev_loss"].append(x["net"] / 1e9)
    prev[key] = x
out["reentry_price_vs_prev_exit_p10_25_50_75_90"] = np.percentile(byk["px_vs_prev_exit"], [10, 25, 50, 75, 90]).round(3).tolist()
out["reentry_after_prev_win"] = dict(n=len(byk["prev_win"]), net=round(sum(byk["prev_win"]), 2), msol=round(1000 * np.mean(byk["prev_win"]), 2))
out["reentry_after_prev_loss"] = dict(n=len(byk["prev_loss"]), net=round(sum(byk["prev_loss"]), 2), msol=round(1000 * np.mean(byk["prev_loss"]), 2))
gb = collections.defaultdict(list)
for x in re:
    g = x["bs"] - x["prev_sell_s"]
    gb["<25" if g < 25 else "25-150" if g < 150 else "150-1000" if g < 1000 else ">=1000"].append(x["net"] / 1e9)
out["reentry_by_gap"] = {k: dict(n=len(v), net=round(sum(v), 2), msol=round(1000 * np.mean(v), 2)) for k, v in gb.items()}
# graduations
gr = [x for x in T if x.get("ssig") in own_sell and "pAMMBa" in own_sell[x["ssig"]]["progs"]]
out["graduation_trips"] = {L.DAY[r]: dict(n=sum(1 for x in gr if x["run"] == r), net=round(sum(x["net"] for x in gr if x["run"] == r) / 1e9, 2)) for r in L.RUNS}
# top trades
for r in L.RUNS:
    v = sorted([x for x in T if x["run"] == r], key=lambda x: -x["net"])[:20]
    out.setdefault("top20", {})[L.DAY[r]] = dict(sum=round(sum(x["net"] for x in v) / 1e9, 2), median_hold=int(np.median([x["hold"] for x in v])),
        entries=dict(collections.Counter(("LAUNCH" if x["age"] <= 50 else "DIP" if (x.get("dump_sol") or 0) >= 0.5 else "other") for x in v)),
        graduated=sum(1 for x in v if x in gr), median_age=int(np.median([x["age"] for x in v])), max_net=round(v[0]["net"] / 1e9, 3))
print(json.dumps(out, indent=1))
json.dump(out, open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/reentry_grad.json", "w"), indent=1)

#!/usr/bin/env python3
# POST-MIGRATION STUDY: rank wallets by post-migration round-trip profit (R2, R3, R4) and flag insiders.
#  insiders = launch creators (all runs), coin creators, create-slot curve buyers ("bundle") of graduated tokens,
#  first-slot buyers of instant graduations, the brand farm wallets, and "transfer sellers" (>=30% of their PumpSwap
#  sell proceeds come from tokens they never bought: tokens moved in from other wallets).
# Output: wallets.json (per wallet per run stats) + printed shortlist of consistent winners.
import json, pickle, collections, sys, os
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/postmig"
COL = "/home/moiz/sniper-data/collect"
RUNDIRS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
SMS = 212.0
FARM = {"6tzAKfHtQA4zLwgaXn97kU5C1dYsKcRy8XZhZUWmWU23", "4G9JAzftaydKjB2558MLnkYw175KMN6NGGgyxkeRuwwA"}
HOURS = {"R2": 21.8, "R3": 25.0, "R4": None}

def typ(t):
    if t["mayhem"]: return "mayhem"
    if t.get("age_s") is not None and t["age_s"] <= 1.0: return "instant"
    return "fast" if (t.get("age_s") or 1e9) < 300 else "slow"

def main():
    creators = set()
    for r, d in RUNDIRS.items():
        for l in open(os.path.join(COL, d, "launches.jsonl")):
            try: c = json.loads(l)
            except Exception: continue
            for k in ("creator", "user", "payer"):
                if c.get(k): creators.add(c[k])
    W = collections.defaultdict(lambda: collections.defaultdict(dict))
    insider = collections.defaultdict(set)
    for w in FARM: insider[w].add("farm")
    for w in creators: insider[w].add("creator")
    for run in ("R2", "R3", "R4"):
        T = [json.loads(l) for l in open(f"{OUT}/{run}_tokens.jsonl")]
        st = pickle.load(open(f"{OUT}/{run}_strs.pkl", "rb")); strs = st["strs"]; gid = {x: j for j, x in enumerate(strs)}
        tm = {gid[t["mint"]]: t for t in T if t["mint"] in gid}
        for t in T:
            if t.get("coin_creator"): insider[t["coin_creator"]].add("coin_creator")
            for w in t.get("insider_set") or []: insider[w].add("bundle")
            if typ(t) == "instant":
                for w in t.get("fb_wallets") or []: insider[w].add("fb_instant")
        tr = dict(np.load(f"{OUT}/{run}_trips.npz")); du = dict(np.load(f"{OUT}/{run}_dumps.npz"))
        pnl = (tr["proceeds"] + tr["mark"] - tr["cost"] - tr["txcost"]) / 1e9
        hold = np.where(tr["open"] == 0, (tr["arr_out"] - tr["arr_in"]) / 1000, np.nan)
        ty = np.array([typ(tm[m]) if m in tm else "?" for m in tr["mint"].tolist()])
        u = tr["user"]
        o = np.argsort(u, kind="stable"); us = u[o]
        st_ = np.r_[0, np.nonzero(np.diff(us))[0] + 1]; en = np.r_[st_[1:], len(us)]
        dproc = collections.Counter()
        for uu, p in zip(du["user"].tolist(), du["proceeds"].tolist()): dproc[uu] += p
        for a, b in zip(st_.tolist(), en.tolist()):
            ix = o[a:b]; w = strs[int(us[a])]
            sp = tr["proceeds"][ix].sum()
            d = dict(n=int(len(ix)), n_open=int(tr["open"][ix].sum()), pnl=float(pnl[ix].sum()), pnl_closed=float(pnl[ix][tr["open"][ix] == 0].sum()),
                     vol=float(tr["cost"][ix].sum() / 1e9), tokens=int(len(np.unique(tr["mint"][ix]))),
                     size_med=float(np.median(tr["cost"][ix]) / 1e9), delay_med=float(np.median(tr["delay"][ix]) * SMS / 1000),
                     hold_med=float(np.nanmedian(hold[ix])) if np.isfinite(hold[ix]).any() else None,
                     win=float((pnl[ix] > 0).mean()), slot0=float((tr["delay"][ix] == 0).mean()),
                     types={k: int((ty[ix] == k).sum()) for k in ("instant", "fast", "slow", "mayhem")},
                     pnl_types={k: round(float(pnl[ix][ty[ix] == k].sum()), 3) for k in ("instant", "fast", "slow", "mayhem")},
                     dump_proc=float(dproc.get(int(us[a]), 0) / 1e9), sell_proc=float(sp / 1e9), txcost=float(tr["txcost"][ix].sum() / 1e9))
            if d["dump_proc"] > 0.3 * (d["dump_proc"] + d["sell_proc"]) and d["dump_proc"] > 1: insider[w].add("transfer_seller")
            W[w][run] = d
        print(run, "wallets", len(st_), flush=True)
    out = {}
    for w, runs in W.items():
        out[w] = dict(runs=runs, insider=sorted(insider.get(w, ())))
    json.dump(out, open(f"{OUT}/wallets.json", "w"))
    # consistent winners: >=20 trips in R2 and R3, profit in both, not insider
    rows = []
    for w, x in out.items():
        r2 = x["runs"].get("R2"); r3 = x["runs"].get("R3"); r4 = x["runs"].get("R4")
        if not r2 or not r3: continue
        if r2["n"] < 20 or r3["n"] < 20: continue
        if r2["pnl"] <= 0 or r3["pnl"] <= 0: continue
        rows.append((r2["pnl"] + r3["pnl"], w, x))
    rows.sort(reverse=True)
    print("consistent winners (>=20 trips and profit in R2 and R3):", len(rows), " non-insider:", sum(1 for r in rows if not r[2]["insider"]))
    tot = collections.Counter()
    for s, w, x in rows:
        tot["all"] += s
        if not x["insider"]: tot["clean"] += s
    print("their R2+R3 profit: all", round(tot["all"]), "non-insider", round(tot["clean"]))
    for s, w, x in rows[:60]:
        r2, r3, r4 = x["runs"]["R2"], x["runs"]["R3"], x["runs"].get("R4") or {}
        print(f"{w[:10]} ins={','.join(x['insider']) or '-':22s} R2 {r2['pnl']:+8.1f}/{r2['n']:5d} R3 {r3['pnl']:+8.1f}/{r3['n']:5d} R4 {r4.get('pnl', 0):+7.1f}/{r4.get('n', 0):4d} "
              f"size {r3['size_med']:.2f} delay {r3['delay_med']:.0f}s hold {r3['hold_med'] if r3['hold_med'] is None else round(r3['hold_med'])}s win {r3['win']:.2f} slot0 {r3['slot0']:.2f} "
              f"types {r3['types']} pt {r3['pnl_types']}")

if __name__ == "__main__":
    main()

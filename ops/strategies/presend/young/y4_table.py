#!/usr/bin/env python3
"""YOUNG step 4: one row per UNIQUE trigger (dedup by trigger sig across FRA/AMS) with arm-time features and the expected
outcome of many recipes (ysim.esim, size 0.696, TP 20 / SL 50 unless the recipe changes it, fixed cost 3.52 mSOL per fill,
failed tries 5,120 lamports x tries). Out: /home/it/sniper-data/presend_young/table.pkl"""
import pickle, collections, sys
from multiprocessing import Pool
from ylib import *
from ysim import esim, LIVE_MIX
meta, R, TP = load()
SIZE = 0.696; COST = 0.00352
# failed tries per armed slot, MEASURED: live attempts per armed window (presend_live_disarm.attempts) / window slots ~ see y4 log
TPS = 5.0  # MEASURED r36: 19,834 landed failed tries / 415 windows ~ 48 per window of ~8-10 slots

def shift(mix, d): return [(h + d, p, w) for h, p, w in mix]
EXITS = {
    "base": dict(mix=LIVE_MIX, tp=0.20, sl=0.50),
    "fast1": dict(mix=[(1, 0.66, 0.7), (2, 0.39, 0.3)], tp=0.20, sl=0.50),   # INFERRED: sell decided at fill (+100 ms or less)
    "slow+1": dict(mix=shift(LIVE_MIX, 1), tp=0.20, sl=0.50),
    "slow+3": dict(mix=shift(LIVE_MIX, 3), tp=0.20, sl=0.50),             # ~1.3 s
    "slow+6": dict(mix=shift(LIVE_MIX, 6), tp=0.20, sl=0.50),             # ~2.5 s
    "slow+12": dict(mix=shift(LIVE_MIX, 12), tp=0.20, sl=0.50),           # ~5 s
    "tp05": dict(mix=LIVE_MIX, tp=0.05, sl=0.50),
    "tp10": dict(mix=LIVE_MIX, tp=0.10, sl=0.50),
    "slow+6tp10": dict(mix=shift(LIVE_MIX, 6), tp=0.10, sl=0.50),
    "slow+12tp10": dict(mix=shift(LIVE_MIX, 12), tp=0.10, sl=0.30),
}
ENTRIES = {
    "e88": dict(lim_mult=0.88),
    "e80": dict(lim_mult=0.80),
    "e75": dict(lim_mult=0.75),
    "e70": dict(lim_mult=0.70),
    "e88w": dict(lim_mult=0.88, dumper="whale"),
    "e88nw": dict(lim_mult=0.88, dumper="notwhale"),
    "e88s2": dict(lim_mult=0.88, need_sells=2),
    "e80s2": dict(lim_mult=0.80, need_sells=2),
    "e88nowst": dict(lim_mult=0.88, whale_stop=False),
    "e80w": dict(lim_mult=0.80, dumper="whale"),
}
SIZES = {"s0.3": 0.3}


def feats(r, tp):
    pre = [x for x in tp if (x[0], x[1], x[2]) < (r["slot"], r["idx"], r.get("j", 0))]
    first = tp[0] if tp else None
    cs = r["slot"] - r["age"]
    pre_cs = [x for x in pre if x[0] == cs]
    dev = first[8] if first and first[0] == cs else None
    f = {"dev": dev, "dev_sol": first[4] / 1e9 if dev else None, "whale_is_dev": dev == r["wallet"],
         "n_pre": len(pre), "n_pre_buyers": len({x[8] for x in pre if x[3]}), "sol_pre": sum(x[4] for x in pre if x[3]) / 1e9,
         "n_cs_buyers": len({x[8] for x in pre_cs if x[3]}), "sells_pre": sum(1 for x in pre if not x[3]),
         "whale_prev_buys": sum(1 for x in pre if x[8] == r["wallet"] and x[3]),
         "vsol_trig": r["vsol"] / 1e9, "whale_sol": r["sol"] / 1e9, "pct": r["pct"], "hour": pkt(r["t"]).hour,
         "post_trig_buys_same_slot": sum(1 for x in tp if x[0] == r["slot"] and (x[1], x[2]) > (r["idx"], r.get("j", 0)) and x[3] and x[8] not in OURS)}
    return f


def one(r):
    tp = TP.get(r["sig"])
    if not tp: return None
    out = {"sig": r["sig"], "run": r["reg"] + r["run"], "reg": r["reg"], "t": r["t"], "age": r["age"], "wallet": r["wallet"], "mint": r["mint"],
           "q_all4": r["q_all4"], "live": r["live"], "test": is_test(r), "lp": sum(x for x in r["real"] if x is not None) / 1e9, "lf": len(r["lfill"])}
    out.update(feats(r, tp))
    res = {}
    for en, ek in ENTRIES.items():
        for xn, xk in EXITS.items():
            if en != "e88" and xn not in ("base", "slow+6", "tp10", "fast1"): continue
            res[(en, xn, SIZE)] = esim(r, tp, size=SIZE, cost_rt=COST, tries_per_slot=TPS, **ek, **xk)
    for sn, sz in SIZES.items():
        for en in ("e88", "e80"):
            res[(en, "base", sz)] = esim(r, tp, size=sz, cost_rt=COST, tries_per_slot=TPS, **ENTRIES[en], **EXITS["base"])
    out["res"] = res
    return out


if __name__ == "__main__":
    ages = set(int(a) for a in sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    seen = set(); todo = []
    for r in sorted(R, key=lambda r: (r["live"] != "armed", r["t"])):
        if r["sig"] in seen: continue
        seen.add(r["sig"])
        if ages is None or min(r["age"], 99) in ages or (99 in ages and r["age"] >= 2): todo.append(r)
    print("unique triggers", len(seen), "todo", len(todo), flush=True)
    with Pool(6) as p: rows = [x for x in p.map(one, todo, chunksize=50) if x]
    tag = sys.argv[1].replace(",", "_") if len(sys.argv) > 1 else "all"
    pickle.dump(rows, open(f"{D}/table_{tag}.pkl", "wb"))
    print("rows", len(rows))

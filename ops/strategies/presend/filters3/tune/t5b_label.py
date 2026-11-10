#!/usr/bin/env python3
"""TUNE t5b: QUIET3-B / creator-ledger sensitivity to the FOLLOWED label: strict (a buy by others after our buy up to our sell landing)
vs QUIET3's (its fol list reaches past our sell: up to sell slot + 2). Also adds followed2 to pos_all.pkl."""
import sys, pickle
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/it/sniper-data/filters3/tune/pos_all.pkl", "rb"))
for r in P:
    tp = T.load(r["run"])["tape"].get(r["mint"], [])
    excl = T.OURS | {r["whale"]} | {h.get("w") for h in r["arm_holders"]}
    fs, fi, ss = r["fill_slot"] or 0, r["fill_idx"] or 0, r["sell_slot"] or ((r["fill_slot"] or 0) + 3)
    r["followed2"] = any(x[3] and x[2] not in excl and (x[0], x[1]) > (fs, fi) and x[0] <= ss + 2 for x in tp)
pickle.dump(P, open("/home/it/sniper-data/filters3/tune/pos_all.pkl", "wb"))
import importlib.util
spec = importlib.util.spec_from_file_location("c", "/home/it/sniper/ops/strategies/presend/filters3/tune/t5_creator.py")

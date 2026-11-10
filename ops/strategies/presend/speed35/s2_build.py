#!/usr/bin/env python3
"""SPEED35 step 2: trigger rows + chain tapes for AMS r36 and r37 (r37 = fresh read-only copy, tape from the recorder chunks
decoded into /home/it/sniper-data/speed35/tab). r36 rows/tapes reused from the YOUNG study (trig.json, tapes.pkl).
Rows use YOUNG's extraction (y1_extract.run). Out: /home/it/sniper-data/speed35/rows.pkl {rows, tapes, maxi(slot->max idx)}"""
import sys, json, pickle, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/young")
import y1_extract
D = "/home/it/sniper-data/speed35"; Y = "/home/it/sniper-data/presend_young"
T = json.load(open(f"{Y}/trig.json"))["rows"]; TP = pickle.load(open(f"{Y}/tapes.pkl", "rb"))
rows = [r for r in T if r["reg"] == "AMS" and r["run"] == "r36"]
tapes = {r["sig"]: TP.get(r["sig"]) for r in rows}
m, r37 = y1_extract.run("AMS", "r37", f"{D}/dip_ams_r37.jsonl")
for r in r37:
    if r["sh_fill"]: r["sh_fill"] = {k: r["sh_fill"].get(k) for k in ("entry", "m", "lim", "ref", "s_in", "seller_is_whale", "slots_after_trigger", "drop_pct")}
tr = np.load(f"{D}/tab/trades.npy"); ids = json.load(open(f"{D}/tab/ids.json")); gid = {k: i for i, k in enumerate(ids)}
smax = int(tr["slot"][-1])
order = np.argsort(tr["mint"], kind="stable"); ms = tr["mint"][order]
keep = []
for r in r37:
    if r["slot"] + 60 > smax or r["mint"] not in gid: continue
    g = gid[r["mint"]]; a, b = np.searchsorted(ms, g), np.searchsorted(ms, g, side="right")
    t = tr[np.sort(order[a:b])]; t = t[t["slot"] <= r["slot"] + 60]
    tapes[r["sig"]] = [(int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]) for x in t]
    keep.append(r)
rows += keep
maxi = {}
z = np.load("/home/it/sniper-data/presend_quiet3/chain.npz")
for s, i, bt in z["blocks"].tolist(): maxi[s] = i
z = np.load(f"{Y}/ext/chain.npz")
for s, i, bt in z["blocks"].tolist(): maxi[s] = max(i, maxi.get(s, 0))
sl = np.load(f"{D}/tab/slots.npy")
for s, i in zip(sl["slot"].tolist(), sl["maxi"].tolist()): maxi[s] = max(i, maxi.get(s, 0))
pickle.dump({"rows": rows, "tapes": tapes, "maxi": maxi, "r37_end_slot": smax - 60}, open(f"{D}/rows.pkl", "wb"))
for rn in ("r36", "r37"):
    R = [r for r in rows if r["run"] == rn]; A = [r for r in R if r["live"] == "armed"]
    print(rn, "triggers", len(R), "armed", len(A), "with tape", sum(1 for r in A if tapes.get(r["sig"])), "live fills", sum(len(r["lfill"]) for r in A),
          "live real", round(sum(sum(x for x in r["real"] if x is not None) for r in A) / 1e9, 3))

#!/usr/bin/env python3
# READ-ONLY, offline. For every REAL sell of the wallets on tokens with a market path, the most likely trigger, from what
# happened on chain just before it (INFERRED labels from MEASURED context):
#   LIGHT  first partial sell <= 8 slots after the buy
#   DEV    a dev (launch signer/creator) sell landed after our previous sell and <= 2 slots before this one
#   TP     price before our sell is at the running high (>= 98% of the peak since our buy) and >= +10% vs entry
#   SL     price <= 0.92 x entry (no dev trigger)
#   DD     price >= 3% under the running peak (pullback), above the SL zone
#   TIME   final clear 270-300 slots (~60 s) after the buy or after the last TP sell, with no other trigger
# Also the reaction lag to dev sells (slots, and tx-index gap when in the same slot).
import sys, os, json, pickle, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

cases = pickle.load(open(os.path.join(EXITS, "cache", "cases.pkl"), "rb"))
lab = collections.Counter(); lab_fin = collections.Counter(); lags = []; same_slot_idx = []; tp_lags = []
pnl_by = collections.defaultdict(float); rows = []
for c in cases:
    W = WALLETS[c["w"]]; tr = c["tr"]; dev = c["dev"]
    kb = next(k for k, t in enumerate(tr) if t["sig"] == c["rt"]["legs"][0]["sig"] and t["user"] == W)
    entry = tr[kb]["sol"] / tr[kb]["tok"]; peak = tr[kb]["vsol"] / tr[kb]["vtok"]
    own = [k for k in range(kb + 1, len(tr)) if tr[k]["user"] == W and not tr[k]["buy"]]
    if not own: continue
    last_own = kb; last_tp_slot = tr[kb]["s"]; n_sells = len(own)
    for n, k in enumerate(own):
        t = tr[k]; p = tr[k - 1]["vsol"] / tr[k - 1]["vtok"]
        for x in tr[last_own + 1:k]:
            if x["user"] != W: peak = max(peak, x["vsol"] / x["vtok"])
        devs = [x for x in tr[last_own + 1:k] if x["user"] in dev and not x["buy"] and t["s"] - x["s"] <= 2]
        m = p / entry; fin = n == n_sells - 1
        held = sum(x["tok"] if x["buy"] else -x["tok"] for x in tr[kb:k] if x["user"] == W)
        frac = t["tok"] / held if held > 0 else 1
        if n == 0 and t["s"] - tr[kb]["s"] <= 8 and not fin: L = "LIGHT"
        elif devs: L = "DEV"; d = devs[-1]; lags.append(t["s"] - d["s"]); same_slot_idx.append(t["i"] - d["i"]) if (t["s"] == d["s"] and t["i"] < 10**6 and d["i"] < 10**6) else None
        elif fin and (265 <= t["s"] - tr[kb]["s"] <= 300 or 265 <= t["s"] - last_tp_slot <= 300) and m > 0.92: L = "TIME"
        elif p >= 0.98 * peak and m >= 1.10: L = "TP"
        elif m <= 0.92: L = "SL"
        elif p <= 0.97 * peak: L = "DD"
        else: L = "OTHER"
        if L == "TP":
            last_tp_slot = t["s"]
            pk = [x for x in tr[kb + 1:k] if x["user"] != W and x["buy"]]
            if pk:
                lastpk = max(pk, key=lambda x: (x["vsol"] / x["vtok"], -x["s"]))
                tp_lags.append(t["s"] - lastpk["s"])
        lab[L] += 1
        if fin: lab_fin[L] += 1
        rows.append(dict(w=c["w"], mint=c["mint"], sig=t["sig"], dslot=t["s"] - tr[kb]["s"], frac=frac, mult=m, label=L, final=fin))
        last_own = k
print(f"{len(cases)} tokens with market paths, {sum(lab.values())} real sells")
print("all sells by inferred trigger:", dict(lab.most_common()))
print("FINAL clears by inferred trigger:", dict(lab_fin.most_common()))
print(f"reaction lag to the dev sell (slots): {dict(sorted(collections.Counter(lags).items()))}; same-slot tx-index gap quantiles "
      f"{[sorted(same_slot_idx)[int(q * len(same_slot_idx))] for q in (0.1, 0.25, 0.5, 0.75, 0.9)] if same_slot_idx else None}")
print(f"TP sells: slots after the peak-setting buy: {dict(sorted(collections.Counter(min(x, 10) for x in tp_lags).items()))}")
fr = collections.defaultdict(list)
for r in rows: fr[r["label"]].append(r["frac"])
print("median fraction sold by trigger:", {k: round(statistics.median(v), 2) for k, v in fr.items()})
mm = collections.defaultdict(list)
for r in rows: mm[r["label"]].append(r["mult"])
print("median price multiple (vs entry) by trigger:", {k: round(statistics.median(v), 3) for k, v in mm.items()})
json.dump(rows, open(os.path.join(EXITS, "triggers.json"), "w"))

#!/usr/bin/env python3
"""FORWARD step 0: the bad-creator ledger seed for the dip27 forward test (WHO's G-cr lead, rebuilt by VERIFY).
From VERIFY's tables (every live window of 26 runs up to AMS r38): per creator, the values of our past fills where that creator held
>= 3% at arm (scaled to 0.696 SOL, minus the window's failed-try fees: VERIFY's `v`). Read-only.
Out: /home/it/sniper-data/prevent/forward/gcr_seed.json {creator: {"n": fills, "sum": SOL}}"""
import pickle, json, collections
V = "/home/it/sniper-data/prevent/verify"
T = pickle.load(open(f"{V}/tables.pkl", "rb")); F = pickle.load(open(f"{V}/feats.pkl", "rb"))
tw = {(x["run"], x["w"]): x for x in T["trades"]}
led = collections.defaultdict(lambda: [0, 0.0])
for w in T["wins"]:
    x = tw.get((w["run"], w["w"])); f = F.get((w["run"], w["w"]), {})
    if not x or not f.get("ok") or not f.get("creator") or f.get("cre_pct", 0) < 3: continue
    v = -w["wfee"] + (x["s"] if x["kind"] == "t2" else x["unit"])
    led[f["creator"]][0] += 1; led[f["creator"]][1] += v
out = {c: {"n": n, "sum": round(s, 6)} for c, (n, s) in led.items()}
json.dump(out, open("/home/it/sniper-data/prevent/forward/gcr_seed.json", "w"), indent=0)
bad = sorted(((c, d) for c, d in out.items() if d["n"] >= 2 and d["sum"] <= -0.05), key=lambda kv: kv[1]["sum"])
print(f"{len(out)} creators, {len(bad)} listed now (>= 2 fills, sum <= -0.05):", ", ".join(f"{c[:8]} {d['n']}/{d['sum']:+.3f}" for c, d in bad[:12]))

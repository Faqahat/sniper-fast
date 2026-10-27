#!/usr/bin/env python3
# r26: offline picks (study envelope + live IMIT1 score >= top4, near leader, server running) vs the engine's own pass flags.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r08_forecast import load_dumps
F = json.load(open(f"{R.WORK}/fires.json")); runs = {(r["srv"], r["run"]): r for r in F["runs"]}
D = load_dumps(); THR4 = 0.21088520504965255
allrec = collections.defaultdict(set)
for srv, rn, base in R.RUN_FILES:
    for l in open(f"{R.LIVE}/{base}.jsonl"):
        if '"dump"' not in l[:400]: continue
        o = json.loads(l)
        if o.get("ev") == "dump": allrec[srv].add((o["mint"], o["slot"], o["idx"]))
passed = {srv: {(o["mint"], o["slot"], o["idx"]) for (s, rn), lst in D.items() if s == srv for o in lst} for srv in ("FRA", "AMS")}
meta = json.load(open(f"{R.WORK}/NEW/dd1_meta.json")); FN = meta["feats"] + meta["xf"]; FNI = {k: i for i, k in enumerate(FN)}
c = collections.Counter()
for tag in ("OLD", "NEW"):
    TP = S.Tapes(tag); z = np.load(f"{R.WORK}/{tag}/dd1_{tag}.npz"); d = {k: z[k] for k in ("k", "tok", "s", "bt", "F", "X", "f1")}
    X = np.concatenate([d["F"], d["X"]], 1); f = lambda k: X[:, FNI[k]]
    env = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    for r in np.flatnonzero(env & np.isfinite(d["f1"]) & (d["f1"] >= THR4)).tolist():
        t = TP.meta[int(d["tok"][r])]; tp = TP.token(int(d["tok"][r])); j0 = int(d["k"][r]) - tp["o"]
        key = (t["m"], int(d["s"][r]), int(tp["i"][j0])); bt = int(d["bt"][r]) or None
        if bt is None: continue
        for srv in ("FRA", "AMS"):
            rn = next((k[1] for k, ru in runs.items() if k[0] == srv and ru["start"] <= bt <= (ru["end"] or R.pk("10-25 07:50"))), None)
            if rn is None: continue
            if tag == "OLD" and bt >= R.pk("10-24 19:26") and t["m"] in TP.mint2t and False: continue
            near = R.leader(key[1]) in R.near_list(R.near_name(srv, rn))
            if not near: continue
            c[(srv, rn, "engine passed" if key in passed[srv] else ("engine saw, did not pass" if key in allrec[srv] else "engine never saw (feed gap / not tracked)"))] += 1
for k in sorted(c): print(k, c[k])

# why not passed: the server's own dump record
rec = {}
for srv, rn, base in R.RUN_FILES:
    for l in open(f"{R.LIVE}/{base}.jsonl"):
        if '"dump"' not in l[:400]: continue
        o = json.loads(l)
        if o.get("ev") == "dump": rec[(srv, o["mint"], o["slot"], o["idx"])] = o
why = collections.Counter()
for tag in ("OLD", "NEW"):
    TP = S.Tapes(tag); z = np.load(f"{R.WORK}/{tag}/dd1_{tag}.npz"); d = {k: z[k] for k in ("k", "tok", "s", "bt", "F", "X", "f1")}
    X = np.concatenate([d["F"], d["X"]], 1); f = lambda k: X[:, FNI[k]]
    env = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    for r in np.flatnonzero(env & np.isfinite(d["f1"]) & (d["f1"] >= THR4)).tolist():
        t = TP.meta[int(d["tok"][r])]; tp = TP.token(int(d["tok"][r])); j0 = int(d["k"][r]) - tp["o"]
        key = (t["m"], int(d["s"][r]), int(tp["i"][j0])); bt = int(d["bt"][r]) or None
        if bt is None: continue
        for srv in ("FRA", "AMS"):
            rn = next((k[1] for k, ru in runs.items() if k[0] == srv and ru["start"] <= bt <= (ru["end"] or R.pk("10-25 07:50"))), None)
            if rn is None or R.leader(key[1]) not in R.near_list(R.near_name(srv, rn)): continue
            if key in passed[srv] or key not in allrec[srv]: continue
            o = rec[(srv,) + key]
            why[(srv, rn, "launch_ok False" if not o.get("launch_ok") else ("own score below the bar" if o.get("score") is not None and o["score"] < THR4 else ("M2 gate" if o.get("m2_mode") == "gate" else "other")))] += 1
print(dict(why))

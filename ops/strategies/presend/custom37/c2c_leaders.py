#!/usr/bin/env python3
"""CUSTOM37 step 2c [MEASURED, arm-time]: the leader-client schedule of each window's slots (trigger slot .. +10), from the leader
client every presend_attempt of the run recorded for its send slot (the engine's leader schedule; leaders hold 4-slot groups, so a
slot without an attempt takes its group's client). Features: share of the 11 slots led by Firedancer-family (Firedancer,
HarmonicFiredancer, FireBAM), BAM (AgaveBam, FireBAM), Jito (JitoLabs), Harmonic (HarmonicAgave, HarmonicFiredancer); first-slot client.
Out: /home/moiz/sniper-data/custom37/leaders_<run>.pkl {(ses, w): feats}"""
import sys, json, pickle
D = "/home/moiz/sniper-data/custom37"
from c1_extract import RUNS
FAM = {"fd": ("Firedancer", "HarmonicFiredancer", "FireBAM"), "bam": ("AgaveBam", "FireBAM"), "jito": ("JitoLabs",), "harm": ("HarmonicAgave", "HarmonicFiredancer")}
for run in sys.argv[1:]:
    sc = {}
    for line in open(RUNS[run][1]):
        if '"ev":"presend_attempt"' not in line: continue
        r = json.loads(line)
        if r.get("client"): sc[r["slot"]] = r["client"]
    grp = {}
    for s, c in sc.items(): grp.setdefault(s // 4, c)
    X = pickle.load(open(f"{D}/win_{run}.pkl", "rb"))
    out = {}
    for W in X["wins"]:
        s0 = W["trig"]["slot"]; cl = [sc.get(s) or grp.get(s // 4) for s in range(s0, s0 + 11)]
        known = [c for c in cl if c]
        if len(known) < 6: continue
        out[(W["ses"], W["w"])] = {k: sum(1 for c in known if c in v) / len(known) for k, v in FAM.items()} | {"first": cl[0]}
    pickle.dump(out, open(f"{D}/leaders_{run}.pkl", "wb"))
    print(run, "windows", len(X["wins"]), "with leader schedule", len(out), flush=True)

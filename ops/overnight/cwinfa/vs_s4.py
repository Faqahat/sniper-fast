#!/usr/bin/env python3
# READ-ONLY, offline: does CWiNFA's deployer list add anything on top of the frozen S4G strategy (9Sh2fd + DGmspi list +
# gate)? Uses core/exp.py's walk-forward harness (imported read-only, run from core/ for its relative paths) with OUR replay
# outcomes (cwinfa/replay_all.json, same S4 mechanics) swapped in, and CWiNFA's attempts from our collector scan.
import os, sys, json, collections
CORE = "/home/moiz/sniper/ops/overnight/core"; HERE = "/home/moiz/sniper/ops/overnight/cwinfa"
os.chdir(CORE); sys.path.insert(0, CORE)
import exp
RR = json.load(open(os.path.join(HERE, "replay_all.json")))
exp.R = {m: dict(run=r["run"], **{L: dict(ok=r[L]["ok"], **({"0.5": r[L].get("eos05")} if r[L]["ok"] else {})) for L in ("45", "75") if L in r}) for m, r in RR.items()}
C = json.load(open(os.path.join(HERE, "coll_cw.json")))
for m in list(exp.ATT): exp.ATT[m].pop("CWiNFA", None)
for m, v in C.items():
    if v.get("buy") or v.get("failed"): exp.ATT[m]["CWiNFA"] = [1 if v.get("buy") else 0, 0]
S9 = exp.S9; CW = ("CWiNFA",)
V = {"S4G (9Sh2fd+DGmspi list + gate)": lambda st: 0.5 if exp.listed(st, S9) and exp.gate_ok(st) else 0,
     "CWiNFA list + gate": lambda st: 0.5 if exp.listed(st, CW) and exp.gate_ok(st) else 0,
     "union S4 or CWiNFA list + gate": lambda st: 0.5 if (exp.listed(st, S9) or exp.listed(st, CW)) and exp.gate_ok(st) else 0,
     "CWiNFA list + gate, NOT on the S4 list": lambda st: 0.5 if exp.listed(st, CW) and not exp.listed(st, S9) and exp.gate_ok(st) else 0}
out = {}
for Lm in (45, 75):
    for n, f in V.items(): out[f"{n}|{Lm}"] = exp.run(f, Lm, n)
json.dump(out, open(os.path.join(HERE, "vs_s4.json"), "w"), indent=1)

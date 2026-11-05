#!/usr/bin/env python3
"""BIGLOSS b7: score the FROZEN rules once on DEV / VAL / HOLDOUT (reads FROZEN.json; refuses if script hashes differ)."""
import sys, json, hashlib, os
B = "/home/moiz/sniper/ops/strategies/presend/bigloss"
sys.path.insert(0, B)
from bscore import *
from brules import *
FZ = json.load(open(f"{B}/FROZEN.json"))
for fn, h in FZ["sha256"].items():
    got = hashlib.sha256(open(f"{B}/{fn}", "rb").read()).hexdigest()
    if got != h: sys.exit(f"hash mismatch {fn}")
R = load_feats(); H, HR = hours()


def build(spec):
    t = spec["type"]; cut = spec.get("cut", 1.0)
    if t == "dumper":
        return make_dumper(spec["k"], spec["X"], spec["pmin"], win_h=spec.get("win_h"), kinds=tuple(spec["kinds"]),
                           s_min=spec["s_min"], cut=cut)
    if t == "creator": return make_creator(spec["k"], spec["X"], cut=cut)
    if t == "ls": return make_feat(lambda r: r.get("ls_sum") is not None and r["ls_sum"] >= spec["L"], kinds=tuple(spec["kinds"]), cut=cut)
    if t == "union": return combine(*[build(s) for s in spec["parts"]], cut=spec.get("cut"))
    if t == "on_top":  # incremental value of 'add' when 'base' is already live: score only positions base keeps
        b = build(spec["base"]); a = build(spec["add"])
        def rule(r, L):
            return 0.0 if b[0](r, L) > 0 else a[0](r, L)
        return rule, a[1]
    raise ValueError(t)


out = {}
for name, spec in FZ["rules"].items():
    res = simulate(R, *build(spec))
    o = report(res, H=H)
    out[name] = o
    print(fmt(name, o))
    for st in ("DEV", "VAL", "HOLD"): print("   ", st, o[st]["per_run"])
json.dump(out, open(f"{D}/final_scores.json", "w"), indent=1)

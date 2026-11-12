#!/usr/bin/env python3
"""dip48 FLOW: the r84 check's fixture. From a run jsonl: per presend_live_fill its position's tape (presend_live_tape: every trade on the
mint while we held it) and the RECOMPUTED outside buy / sell SOL through fill+1 / fill+2 (trades after our fill's (slot, idx, j), ours out).
The engine test feeds the same tape through psflow48's accumulator and must match.  usage: r84_fixture.py RUN.jsonl OUT.json"""
import json, sys
fills, tape = [], {}
for l in open(sys.argv[1]):
    if '"presend_live_fill"' in l:
        r = json.loads(l)
        if r.get("ev") == "presend_live_fill": fills.append(r)
    elif '"presend_live_tape"' in l:
        r = json.loads(l)
        if r.get("ev") == "presend_live_tape": tape.setdefault(r["mint"], []).append(r)
out = []
for f in fills:
    T = sorted(tape.get(f["mint"], []), key=lambda x: (x["slot"], x["idx"], x["j"]))
    ours = next((x["user"] for x in T if x["sig"] == f["sig"]), None)
    if ours is None: continue
    fp = (f["slot"], f["idx"], next(x["j"] for x in T if x["sig"] == f["sig"]))
    rows = [x for x in T if (x["slot"], x["idx"], x["j"]) > fp and x["slot"] <= f["slot"] + 3]
    def tot(n, buy): return sum(x["sol"] for x in rows if x["user"] != ours and x["buy"] == buy and x["slot"] <= f["slot"] + n) / 1e9
    out.append({"w": f["w"], "mint": f["mint"], "kind": f.get("kind", "t2"), "fill": list(fp), "ours": ours,
                "tape": [[x["slot"], x["idx"], x["j"], x["user"], x["buy"], x["sol"], x["vsol"], x["vtok"]] for x in T if x["slot"] <= f["slot"] + 4],
                "want": {"b1": tot(1, True), "b2": tot(2, True), "s1": tot(1, False), "s2": tot(2, False), "n_after": len(rows)}})
json.dump(out, open(sys.argv[2], "w"), separators=(",", ":"))
print(len(out), "fills;", sum(len(x["tape"]) for x in out), "tape rows;", [(x["w"], round(x["want"]["b1"], 3)) for x in out])

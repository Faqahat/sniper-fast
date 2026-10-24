#!/usr/bin/env python3
"""verify_dip / mk_evfile: turn my rebuilt events into the claim's event-file format so the same block CV can be run on them.
pnl[L]["4"] = my gross PnL of the chosen variant - 2 x TXC.
usage: python3 -I -B mk_evfile.py <my events> <out> <variant> <TXC> <filter: claim|std|all> [tmax_unix]"""
import sys, json, gzip
src, out, var, txc, flt = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), sys.argv[5]
tmax = float(sys.argv[6]) if len(sys.argv) > 6 else 1e18
KEEP = ["m", "run", "bt", "age", "sell", "seller", "ins", "xf", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ahead", "px"]
n = 0
with gzip.open(out, "wt") as f:
    for l in gzip.open(src, "rt"):
        r = json.loads(l)
        if r["bt"] + r["age"] > tmax: continue
        if flt == "claim" and not r["cf"]: continue
        if flt == "std" and not (r["cf"] and r["kind"] == "std"): continue
        o = {k: r[k] for k in KEEP}
        o["pnl"] = {L: {"4": round(v[var] - 2 * txc, 6)} for L, v in r["pnl"].items() if var in v}
        f.write(json.dumps(o) + "\n"); n += 1
print("wrote", n, "events", out)

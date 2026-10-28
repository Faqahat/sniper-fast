#!/usr/bin/env python3
"""quick sanity check of a decisions log (read-only): log_D<k>_<tag>.pkl -> counts and one filled re window"""
import pickle, collections, sys
import numpy as np
fn, name = sys.argv[1], sys.argv[2]
L = pickle.load(open(fn, "rb"))[name]
print("re windows", len(L), collections.Counter(r[2].get("why") for r in L).most_common())
f = [r for r in L if r[2].get("filled")]
print("filled", len(f))
if f:
    t, lg, r = f[0]
    print("trig", {k: t[k] for k in ("mint", "slot", "en", "whale_sell", "src", "r2", "k")})
    print("res", {k: v for k, v in r.items() if k != "ex"})
    print("exits", r["ex"])
    for e in lg[:3] + lg[-3:]: print("  ", e)
    g = np.array([x[2]["ex"]["base"]["gross"] for x in f]) / 1e6
    print("gross per fill mSOL mean %.2f median %.2f win %.0f%%" % (g.mean(), np.median(g), 100 * (g > 0).mean()))

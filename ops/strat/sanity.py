import sys, json
sys.path.insert(0, "/root/strat")
from sim import *
n = 0
for x in load():
    if x.get("stage") != 4 or x.get("mayhem") or x["src"] != "truth": continue
    t = Tok(x)
    dk = x["passed"][0]
    i0 = t.st(dk + 2)
    print(x["mint"][:8], "dk", dk, "entry row d", t.ds[i0], "vsol %.2f" % (t.vs[i0] / 1e9), "fee", t.fee[i0])
    H = int(60 / SLOT); i1 = t.st(dk + 2 + H + 2)
    print("   exit row d", t.ds[i1], "vsol %.2f" % (t.vs[i1] / 1e9), "price ratio %.3f" % ((t.vs[i1] / t.vt[i1]) / (t.vs[i0] / t.vt[i0])))
    for sh in (False, True):
        r = trade(t, dk, 1.0, ("time", 60), shift=sh); print("   shift" if sh else "   double", "pnl %+.4f SOL" % r[0])
    # manual: ratio-based gross ignoring impact
    pr = (t.vs[i1] / t.vt[i1]) / (t.vs[i0] / t.vt[i0]); print("   no-impact approx %+.4f" % (pr * (1 - 0.0125) / 1.0125 - 1 - 0.00061))
    n += 1
    if n >= 3: break

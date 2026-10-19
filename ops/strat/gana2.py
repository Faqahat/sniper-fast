# Sub-family: "single-tx graduations" (curve completed by one tx in the 5 min before migration) vs organic graduations.
import sys, json, statistics
src = open("/root/strat/gana.py").read().split("DE = [2")[0]
exec(src.replace("FEE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.012", "FEE = 0.012"))
q = sorted(x["bt"] for x in R); cuts = [q[0], q[len(q) // 3], q[2 * len(q) // 3], q[-1] + 1]
def f3(x):
    for i in range(3):
        if cuts[i] <= x["bt"] < cuts[i + 1]: return i
for name, g in [("single-tx (pre_n300<=2)", lambda x: (x.get("pre_n300") or 0) <= 2), ("organic (pre_n300>=50)", lambda x: (x.get("pre_n300") or 0) >= 50), ("middle", lambda x: 2 < (x.get("pre_n300") or 0) < 50)]:
    G = [x for x in R if g(x)]
    print("==", name, "n", len(G), "per day %.0f" % (len(G) / ((R[-1]["bt"] - R[0]["bt"]) / 3600) * 24))
    for de in (2, 5, 15):
        for dx in (30, 60, 120, 300, 600):
            if dx <= de: continue
            line = []
            for i in range(3):
                line.append("T%d %s" % (i, st([pnl(x, de, dx, 1.0) for x in G if f3(x) == i])))
            print("  in %2ds out %3ds  %s" % (de, dx, " | ".join(line)))

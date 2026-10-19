# single-tx graduations: does pool SOL at +2 s (known at entry) separate rugs? 3 time folds. 1 SOL, double impact, 1.2%/side.
import sys, json, statistics
src = open("/root/strat/gana.py").read().split("DE = [2")[0]
exec(src.replace("FEE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.012", "FEE = 0.012"))
q = sorted(x["bt"] for x in R); cuts = [q[0], q[len(q) // 3], q[2 * len(q) // 3], q[-1] + 1]
def f3(x):
    for i in range(3):
        if cuts[i] <= x["bt"] < cuts[i + 1]: return i
G = [x for x in R if (x.get("pre_n300") or 0) <= 2 and x["st"].get(2)]
print("single-tx with +2s state:", len(G))
for name, g in [("sol@2s<100", lambda x: x["st"][2][0] < 100e9), ("sol@2s 100-200", lambda x: 100e9 <= x["st"][2][0] < 200e9), ("sol@2s>=200", lambda x: x["st"][2][0] >= 200e9)]:
    H = [x for x in G if g(x)]
    print("==", name, "n", len(H))
    for dx in (60, 120, 300, 600):
        print("  in 2s out %3ds  " % dx + " | ".join("T%d %s" % (i, st([pnl(x, 2, dx, 1.0) for x in H if f3(x) == i])) for i in range(3)))
# when do single-tx graduates rug? first delay at which price < 0.3x of +2s price
c = {}
for x in G:
    p2 = x["st"][2][0] / x["st"][2][1]
    for d in [15,30,60,120,300,600,1200,1800,3600]:
        s = x["st"].get(d)
        if s and s[0] / s[1] < 0.3 * p2:
            c[d] = c.get(d, 0) + 1; break
    else:
        c["none<=3600"] = c.get("none<=3600", 0) + 1
print("first delay with price < 0.3x of entry:", sorted(c.items(), key=str))

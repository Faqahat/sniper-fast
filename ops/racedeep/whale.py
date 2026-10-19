#!/usr/bin/env python3
# READ-ONLY. Item 4 (whale-follow) deep dive + item 3 (race tail: runners vs dumps).
import sys, collections, statistics as st, json
sys.path.insert(0, "/root/racedeep")
from rdlib import load, pf, sim, land_time, stats, fmt, EXITS, SLOT
pros = set(json.load(open("/root/race/pros.json")))
U = [o for o in load() if o["in_rand"]]
night = sorted([o for o in U if o["set"] == "night"], key=lambda o: o["slot"])
mid = night[len(night) // 2]["slot"]
hours = (night[-1]["slot"] - night[0]["slot"]) * 0.217 / 3600


def per(o):
    if o["set"] != "night":
        return o["set"]
    return "nightA" if o["slot"] < mid else "nightB"


PER = ("hist", "fwd", "nightA", "nightB")
LAND = {"S+50": ("S", 50), "S+100": ("S", 100), "S1 mid": ("S1", 0.5), "S1 end": ("S1", 1.0)}
XS = ["t1", "t2", "t3", "t5", "t10", "70%1s+trail0.8/40s", "half@1.3 half@2 /10s"]


def whale_j(o, lo, hi, kmax, excl_his=False):
    for j, z in enumerate(o["tr"]):
        if z[1] > kmax:
            return None
        if z[3] == "O" and lo <= z[4] < hi and not (excl_his and z[9]):
            return j
    return None


print(f"night {len(night)} launches, {hours:.2f} h; split at slot {mid}")
print("\n== 4a. whale-follow: first single outside buy in [lo, hi) SOL; enter at landing; realistic 2 SOL. cells = mean (median) per period; blend = 0.4*S+100 + 0.6*S1mid")
for lo, hi in ((2, 3), (3, 5), (5, 10), (3, 10), (4, 10), (5, 99), (10, 99)):
    for kmax, wn in ((0, "S"), (1, "S..S+1"), (2, "S..S+2")):
        g = [(o, whale_j(o, lo, hi, kmax)) for o in U]
        g = [(o, j) for o, j in g if j is not None]
        if len(g) < 15:
            continue
        cnt = collections.Counter(per(o) for o, _ in g)
        nn = cnt["nightA"] + cnt["nightB"]
        print(f"\n-- whale [{lo},{hi}) SOL in {wn}: n {dict(cnt)} | night {nn / hours * 24:.0f}/day | race {sum(o['race'] for o, _ in g) / len(g):.0%} | "
              f"med pf at whale {st.median(o['tr'][j][8] ** 2 / o['base'] ** 2 for o, j in g):.2f}x | whale=4yFAz {sum(o['tr'][j][9] for o, j in g)} | "
              f"top payers {collections.Counter(o['tr'][j][5][:6] for o, j in g).most_common(4)}")
        for xn in XS:
            cells = []
            for ln in list(LAND) + ["blend"]:
                pc = []
                for p in PER:
                    if ln == "blend":
                        v = [0.4 * sim(o, land_time(o, j, LAND["S+100"]), EXITS[xn]) + 0.6 * sim(o, land_time(o, j, LAND["S1 mid"]), EXITS[xn]) for o, j in g if per(o) == p]
                    else:
                        v = [sim(o, land_time(o, j, LAND[ln]), EXITS[xn]) for o, j in g if per(o) == p]
                    pc.append(f"{st.mean(v):+5.1%}" if v else "  -  ")
                cells.append(f"{ln}: " + "/".join(pc))
            print(f"   {xn:20} " + " | ".join(cells))

print("\n== 4b. post-whale drift (no costs): median & mean price ratio p(t_whale + dt) / p(just after whale), whale [3,10) in S")
g = [(o, whale_j(o, 3, 10, 0)) for o in U]
g = [(o, j) for o, j in g if j is not None]
for dt in (25, 50, 100, 217, 500, 1000, 2000, 3000, 5000, 10000):
    r = [pf(o, o["tr"][j][0] + dt) / pf(o, o["tr"][j][0] + 1e-6) for o, j in g]
    print(f"   +{dt:5} ms: med {st.median(r):.3f} mean {st.mean(r):.3f} share up {sum(x > 1 for x in r) / len(r):.0%} (n={len(r)})")

print("\n== 3. race tail: among hindsight RACES, runner = max price in (end S+1, 30 s] >= 2x the price at end S+1")
R = [o for o in U if o["race"]]
def feat(o):
    tS1 = o["tS"] + SLOT
    p1 = pf(o, tS1)
    mx = max([(v / o["base9"]) ** 2 for t, v in zip(o["pt"], o["pv"]) if tS1 < t <= 30000] or [p1])
    zs = [z for z in o["tr"] if z[1] <= 1]
    out = [z for z in zs if z[3] == "O"]
    zS = [z for z in o["tr"] if z[1] == 0 and z[3] == "O"]
    return dict(run=mx / p1 >= 2, peak=mx / p1, p1=p1, n=len({z[5] for z in out}), sol=sum(z[4] for z in out), maxb=max([z[4] for z in out], default=0),
                nS=len({z[5] for z in zS}), solS=sum(z[4] for z in zS), sells=sum(z[4] for z in zs if z[3] == "X"), fails=o["n_err_S"],
                his=any(z[9] for z in out), npro=len({z[5] for z in out if z[5] in pros}), dev=o["dev"], glued=o["glued"], gsol=o["gsol"],
                n1=len({z[5] for z in out if z[1] == 1}), sol1=sum(z[4] for z in out if z[1] == 1),
                hip=sum(1 for z in out if z[6] >= 50e6 or z[7] >= 0.005), gateB=o["dev"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12)
F = [(o, feat(o)) for o in R]
run = [f for _, f in F if f["run"]]
dump = [f for _, f in F if not f["run"]]
print(f"   races {len(F)}: runners {len(run)} ({len(run) / len(F):.0%}); median peak/p(S+1) runners {st.median(f['peak'] for f in run):.2f} dumps {st.median(f['peak'] for f in dump):.2f}")
for k in ("p1", "n", "sol", "maxb", "nS", "solS", "n1", "sol1", "sells", "fails", "his", "npro", "dev", "glued", "gsol", "hip", "gateB"):
    a, b = [float(f[k]) for f in run], [float(f[k]) for f in dump]
    print(f"   {k:6} runners med {st.median(a):7.2f} mean {st.mean(a):7.2f} | dumps med {st.median(b):7.2f} mean {st.mean(b):7.2f}")
print("   -- runner rate by bucket")
for k, ths in (("p1", (1.2, 1.5, 2.0, 3.0)), ("sol", (3, 5, 8, 12)), ("n", (3, 5, 8, 12)), ("sol1", (0.5, 1, 2, 4)), ("n1", (1, 2, 4, 6)), ("sells", (0.01, 0.5, 2)), ("dev", (1, 2, 3, 5))):
    for th in ths:
        g1 = [f for _, f in F if f[k] >= th]
        g0 = [f for _, f in F if f[k] < th]
        if g1 and g0:
            print(f"   {k}>={th}: runner {sum(f['run'] for f in g1) / len(g1):4.0%} (n={len(g1)}) vs < : {sum(f['run'] for f in g0) / len(g0):4.0%} (n={len(g0)})")
print("\n   -- 'ride the second wave': enter S+2 (S1 landing after S+1) on races-so-far, exits; by period")
for nm, cond in ((">=3 out & >=3 SOL by S+1", lambda f: f["n"] >= 3 and f["sol"] >= 3), (">=5 out & >=5 SOL by S+1", lambda f: f["n"] >= 5 and f["sol"] >= 5),
                 ("S+1 alone >=2 buyers & >=2 SOL", lambda f: f["n1"] >= 2 and f["sol1"] >= 2), ("S+1 alone >=4 buyers", lambda f: f["n1"] >= 4),
                 ("by S+1 >=3/3 & price <=1.5x", lambda f: f["n"] >= 3 and f["sol"] >= 3 and f["p1"] <= 1.5)):
    g = []
    for o in U:
        f = feat(o)
        if cond(f):
            g.append(o)
    for xn in ("t1", "t3", "t10", "70%1s+trail0.8/40s", "trail0.8/40s"):
        cells = []
        for p in PER:
            v = [sim(o, o["tS"] + SLOT + 0.5 * SLOT, EXITS[xn]) for o in g if per(o) == p]
            cells.append(f"{p} {st.mean(v):+5.1%} (n={len(v)})" if v else f"{p} -")
        print(f"   {nm:32} {xn:20} " + " | ".join(cells))

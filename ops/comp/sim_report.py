# READ-ONLY offline. Task 5/6 report from sim_<SET>.json
import sys, json, statistics as st, random, math, collections
SET = sys.argv[1] if len(sys.argv) > 1 else "r2"
SELL_FEE = 0.002
LANDS = {"land0.006": 0.006, "land0.045": 0.045}
SOLPX = json.load(open("/root/solprice.json")).get("price", 104)
D = json.load(open(f"/root/comp/sim_{SET}.json"))
D.sort(key=lambda r: r["bt"])
n = len(D)
NF = 3
for i, r in enumerate(D): r["fold"] = min(NF - 1, i * NF // n)
SIZES = [0.25, 0.5, 1.0, 2.0, 3.0]
SCEN = ["d8", "d25", "firstout", "d100", "s1", "today"]
EXITS = list(D[0]["r"]["d8|1.0"]["ex"].keys())
rnd = random.Random(1)

def pnl(r, sc, x, ex, land):
    if sc == "today":
        return 0.75 * pnl(r, "d100", x, ex, land) + 0.25 * pnl(r, "s1", x, ex, land)
    v = r["r"][f"{sc}|{x}"]["ex"][ex]
    return v[0] - x - land - SELL_FEE * v[2]

def stats(v):
    v = list(v); m = st.mean(v)
    s = sorted(v)
    ex3 = st.mean(s[:-3]) if len(s) > 5 else float("nan")
    bs = []
    for _ in range(1000):
        smp = [v[rnd.randrange(len(v))] for _ in range(len(v))]
        bs.append(sum(smp) / len(smp))
    bs.sort()
    return dict(mean=m, med=st.median(v), ex3=ex3, win=sum(1 for x in v if x > 0) / len(v), lo=bs[50], hi=bs[949], sd=st.pstdev(v))

print(f"launches {n}; folds by time: " + ", ".join(f"F{f}: {sum(1 for r in D if r['fold']==f)}" for f in range(NF)))
import time as _t
for f in range(NF):
    g = [r for r in D if r["fold"] == f]
    print(f"  F{f}: {_t.strftime('%m-%d %H:%M', _t.gmtime(g[0]['bt']))} → {_t.strftime('%m-%d %H:%M', _t.gmtime(g[-1]['bt']))}")
print("fee rate (pump buy+sell side, per event) q:", sorted(r["fee_rate"] for r in D)[n // 2])
print("entry price vs post-bundle (median) by scenario @1 SOL:", {sc: round(st.median(r["r"][f"{sc}|1.0"]["entry_vs_pb"] for r in D), 3) for sc in ["d8", "d25", "firstout", "d100", "s1"]})
print("first outsider position in S (median d): %s ; in S share %.2f" % (st.median([r["fo_d"] for r in D if r["fo_d"] is not None] or [-1]), sum(1 for r in D if r["fo_slot"] == 0) / n))
print("peak (first 60 s) vs post-bundle price q:", " ".join(f"{x:.2f}" for x in [sorted(r['peak60_vs_pb'] for r in D)[int(n * p)] for p in (0.1, 0.25, 0.5, 0.75, 0.9)]))

# full table: per scenario x size x land: best exits
OUT = {}
for land_name, L in LANDS.items():
    for sc in SCEN:
        for x in SIZES:
            for ex in EXITS:
                v = [pnl(r, sc, x, ex, L) for r in D]
                s = stats(v)
                s["folds"] = [st.mean([pnl(r, sc, x, ex, L) for r in D if r["fold"] == f]) for f in range(NF)]
                OUT[(land_name, sc, x, ex)] = s

def show(land_name, sc, x, k=6):
    rows = [(ex, OUT[(land_name, sc, x, ex)]) for ex in EXITS]
    rows.sort(key=lambda t: -min(t[1]["folds"]))
    print(f"\n[{land_name}] scenario {sc} size {x} SOL — top exits by worst-fold mean (SOL/trade):")
    print(f"   {'exit':24} {'mean':>7} {'med':>7} {'ex-top3':>7} {'win':>5} {'90%CI':>17}  folds")
    for ex, s in rows[:k]:
        print(f"   {ex:24} {s['mean']:7.4f} {s['med']:7.4f} {s['ex3']:7.4f} {s['win']:5.2f} [{s['lo']:7.4f},{s['hi']:7.4f}]  " + " ".join(f"{f:7.4f}" for f in s["folds"]))
    for ex in ("T1", "T3", "T10", "T30"):
        s = OUT[(land_name, sc, x, ex)]
        print(f"   ref {ex:20} {s['mean']:7.4f} {s['med']:7.4f} {s['ex3']:7.4f} {s['win']:5.2f} [{s['lo']:7.4f},{s['hi']:7.4f}]  " + " ".join(f"{f:7.4f}" for f in s["folds"]))

for land_name in LANDS:
    for sc in ["d8", "d25", "today"]:
        for x in (0.5, 1.0, 2.0):
            show(land_name, sc, x, 5)

# OOS: choose the exit on 2 folds, evaluate on the held-out fold (leave-one-fold-out), per scenario x size x land
print("\n=== Leave-one-fold-out exit selection (choose by mean on other folds; report held-out mean) ===")
print(f"{'land':10} {'scen':9} " + " ".join(f"{x:>14}" for x in SIZES))
for land_name, L in LANDS.items():
    for sc in SCEN:
        cells = []
        for x in SIZES:
            held = []; picks = []
            for f in range(NF):
                tr = [r for r in D if r["fold"] != f]; te = [r for r in D if r["fold"] == f]
                best = max(EXITS, key=lambda ex: st.mean(pnl(r, sc, x, ex, L) for r in tr))
                picks.append(best)
                held += [pnl(r, sc, x, best, L) for r in te]
            cells.append(f"{st.mean(held):+.4f}/{collections.Counter(picks).most_common(1)[0][0][:6]}")
        print(f"{land_name:10} {sc:9} " + " ".join(f"{c:>14}" for c in cells))

# robust exit across all scenarios: count positive-fold cells
print("\n=== Exit robustness: per exit, # of (scenario in d8,d25,today x size 0.5,1,2 x land) cells with ALL folds > 0, and mean PnL% at 1 SOL ===")
sc_list = ["d8", "d25", "firstout", "today"]
rob = []
for ex in EXITS:
    k = 0; tot = 0
    for land_name in LANDS:
        for sc in sc_list:
            for x in (0.5, 1.0, 2.0):
                tot += 1
                if min(OUT[(land_name, sc, x, ex)]["folds"]) > 0: k += 1
    rob.append((ex, k, tot, OUT[("land0.006", "d25", 1.0, ex)]["mean"], OUT[("land0.006", "today", 1.0, ex)]["mean"], OUT[("land0.045", "d8", 1.0, ex)]["mean"]))
rob.sort(key=lambda t: (-t[1], -t[3]))
print(f"   {'exit':24} {'cells+':>7} {'d25@1 L.006':>12} {'today@1 L.006':>13} {'d8@1 L.045':>11}")
for t in rob[:14]:
    print(f"   {t[0]:24} {t[1]:3d}/{t[2]:<3d} {t[3]:12.4f} {t[4]:13.4f} {t[5]:11.4f}")
json.dump({"|".join(map(str, k)): v for k, v in OUT.items()}, open(f"/root/comp/sim_stats_{SET}.json", "w"))

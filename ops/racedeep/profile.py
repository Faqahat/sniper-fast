#!/usr/bin/env python3
# READ-ONLY. Item 1: race vs non-race timeline profile + earliest separating signal. All sets (hist random+his picks, fwd, night).
import sys, collections, statistics as st, json
sys.path.insert(0, "/root/racedeep")
sys.path.insert(0, "/root/race")
from rdlib import load, pf, SLOT
pros = set(json.load(open("/root/race/pros.json")))
U = [o for o in load() if o["in_rand"]]
print("launches", len(U), collections.Counter(o["set"] for o in U), "race rate", f"{sum(o['race'] for o in U) / len(U):.1%}")

CPS = [("create", lambda z, o: False), ("S d<=1", lambda z, o: z[1] == 0 and z[2] <= 1), ("S d<=5", lambda z, o: z[1] == 0 and z[2] <= 5),
       ("S d<=25", lambda z, o: z[1] == 0 and z[2] <= 25), ("S d<=50", lambda z, o: z[1] == 0 and z[2] <= 50),
       ("S d<=100", lambda z, o: z[1] == 0 and z[2] <= 100), ("S d<=200", lambda z, o: z[1] == 0 and z[2] <= 200),
       ("end S", lambda z, o: z[1] == 0), ("end S+1", lambda z, o: z[1] <= 1), ("end S+2", lambda z, o: z[1] <= 2)]


def feats(o, cond):
    zs = [z for z in o["tr"] if cond(z, o)]
    out = [z for z in zs if z[3] == "O"]
    f = {}
    f["n_out"] = len({z[5] for z in out})
    f["n_out_x"] = len({z[5] for z in out if not z[9]})
    f["out_sol"] = sum(z[4] for z in out)
    f["out_sol_x"] = sum(z[4] for z in out if not z[9])
    f["max_buy"] = max([z[4] for z in out], default=0)
    f["n_buy_ge1"] = sum(1 for z in out if z[4] >= 1)
    f["ins_buys"] = sum(1 for z in zs if z[3] == "I")
    f["sells"] = sum(1 for z in zs if z[3] == "X")
    f["sell_sol"] = sum(z[4] for z in zs if z[3] == "X")
    f["ins_sell"] = sum(1 for z in zs if z[3] == "X" and z[5] in (o["creator"],))
    f["fails"] = sum(1 for z in zs if z[3] == "E")
    f["max_cu_M"] = max([z[6] for z in out], default=0) / 1e6
    f["max_tip"] = max([z[7] for z in out], default=0)
    f["hiprio"] = sum(1 for z in out if z[6] >= 50e6 or z[7] >= 0.005)
    f["pros"] = len({z[5] for z in out if z[5] in pros})
    f["his"] = int(any(z[9] for z in out))
    if zs:
        t = zs[-1][0]
        f["t_ms"] = t
    else:
        f["t_ms"] = 0.0
    f["pf"] = pf(o, f["t_ms"]) if zs else pf(o, 0.0)
    return f


print("\n== 1a. timeline: median (mean) of each feature, RACE vs NON-race, at each checkpoint")
FN = ["n_out_x", "out_sol_x", "max_buy", "n_buy_ge1", "ins_buys", "sells", "sell_sol", "fails", "max_cu_M", "max_tip", "hiprio", "pros", "his", "pf", "t_ms"]
R = [o for o in U if o["race"]]
N = [o for o in U if not o["race"]]
allf = {}
for cn, cond in CPS:
    fr = [feats(o, cond) for o in R]
    fn_ = [feats(o, cond) for o in N]
    allf[cn] = (fr, fn_)
    print(f"\n-- {cn}  (race n={len(R)}, non n={len(N)})")
    for k in FN:
        a = [f[k] for f in fr]
        b = [f[k] for f in fn_]
        print(f"   {k:10} race med {st.median(a):8.3f} mean {st.mean(a):8.3f} | non med {st.median(b):8.3f} mean {st.mean(b):8.3f}")

print("\n== 1b. best single threshold per checkpoint: precision (race rate among passers) / recall / pass share / median price at that point")
for cn, (fr, fn_) in allf.items():
    best = []
    for k in FN:
        if k in ("t_ms", "pf"):
            continue
        vals = sorted({f[k] for f in fr + fn_})
        cands = vals if len(vals) < 40 else [vals[int(len(vals) * q / 40)] for q in range(40)]
        for th in cands:
            if th <= 0:
                continue
            tp = sum(1 for f in fr if f[k] >= th)
            fp = sum(1 for f in fn_ if f[k] >= th)
            if tp + fp < 25:
                continue
            prec, rec = tp / (tp + fp), tp / len(fr)
            pfs = [f["pf"] for f in fr + fn_ if f[k] >= th]
            best.append((prec, rec, k, th, tp + fp, st.median(pfs)))
    for minrec in (0.1, 0.3, 0.5):
        c = [b for b in best if b[1] >= minrec]
        if c:
            b = max(c)
            print(f"   {cn:9} recall>={minrec:.1f}: {b[2]} >= {b[3]:.3g}: precision {b[0]:.0%} recall {b[1]:.0%} n={b[4]} | median price at checkpoint {b[5]:.2f}x floor")

print("\n== 1c. median price/floor at each checkpoint (race / non-race) and share of the race's 2-s peak already gone")
for cn, (fr, fn_) in allf.items():
    print(f"   {cn:9} race {st.median(f['pf'] for f in fr):.2f}x  non {st.median(f['pf'] for f in fn_):.2f}x  | t med race {st.median(f['t_ms'] for f in fr):.0f} ms")

print("\n== 1d. who arrives in S (outsider buys, k=0): top wallets by launches, race rate of the launches they buy, med d, med cu (M), tip, SOL")
w = collections.defaultdict(list)
for o in U:
    seen = set()
    for z in o["tr"]:
        if z[1] == 0 and z[3] == "O" and z[5] not in seen:
            seen.add(z[5])
            w[z[5]].append((o["race"], z[2], z[6], z[7], z[4], o["set"]))
base = sum(o["race"] for o in U) / len(U)
rows = []
for p, xs in w.items():
    if len(xs) >= 12:
        rows.append((len(xs), sum(x[0] for x in xs) / len(xs), st.median(x[1] for x in xs), st.median(x[2] for x in xs) / 1e6, st.median(x[3] for x in xs), st.median(x[4] for x in xs), p))
rows.sort(reverse=True)
print(f"   base race rate {base:.1%}; wallets with >=12 launches: {len(rows)}")
for r in rows[:30]:
    print(f"   {r[6][:8]} n={r[0]:4} race {r[1]:4.0%} med d {r[2]:5.0f} cu {r[3]:7.1f}M tip {r[4]:.4f} sol {r[5]:.2f} {'PRO' if r[6] in pros else ''}")
print("   -- highest race rate (n>=15):")
for r in sorted([r for r in rows if r[0] >= 15], key=lambda r: -r[1])[:20]:
    print(f"   {r[6][:8]} n={r[0]:4} race {r[1]:4.0%} med d {r[2]:5.0f} cu {r[3]:7.1f}M tip {r[4]:.4f} sol {r[5]:.2f} {'PRO' if r[6] in pros else ''}")

print("\n== 1e. arrival order inside races: position d of the k-th outsider buy (S only), race vs non")
for kk in (1, 2, 3, 5, 10):
    a = [[z for z in o["tr"] if z[1] == 0 and z[3] == "O"] for o in R]
    b = [[z for z in o["tr"] if z[1] == 0 and z[3] == "O"] for o in N]
    da = [x[kk - 1][2] for x in a if len(x) >= kk]
    db = [x[kk - 1][2] for x in b if len(x) >= kk]
    print(f"   {kk:2}-th outsider in S: race has it {len(da) / len(a):4.0%} med d {st.median(da) if da else -1:5.0f} | non has it {len(db) / len(b):4.0%} med d {st.median(db) if db else -1:5.0f}")
print("\n== 1f. dev / insider behaviour: creator sells in S..S+2 (race vs non)")
for nm, g in (("race", R), ("non", N)):
    cs = [sum(z[4] for z in o["tr"] if z[3] == "X" and z[5] == o["creator"] and z[1] <= 2) for o in g]
    asell = [sum(z[4] for z in o["tr"] if z[3] == "X" and z[1] <= 2) for o in g]
    print(f"   {nm}: creator sold by S+2 in {sum(c > 0 for c in cs) / len(g):.0%} (mean {st.mean(cs):.2f} SOL); any sell by S+2 {sum(c > 0 for c in asell) / len(g):.0%} (mean {st.mean(asell):.2f} SOL)")

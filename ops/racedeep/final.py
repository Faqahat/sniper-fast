#!/usr/bin/env python3
# READ-ONLY. Final tables: (1) decay of each signal's edge with landing delay ("how fast must we be"),
# (2) race-aware EXIT on zero-wait entries (hold races, cut the rest), fit on train, judged on night,
# (3) strategy table with n / mean / median / ex-top3 / win / fires/day / SOL/day at 1 and 2 SOL.
import sys, collections, statistics as st, json
sys.path.insert(0, "/root/racedeep")
from rdlib import load, pf, sim, land_time, stats, fmt, EXITS, SLOT
U = [o for o in load() if o["in_rand"]]
for o in U:
    o["gateB"] = o["dev"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12
night = sorted([o for o in U if o["set"] == "night"], key=lambda o: o["slot"])
mid = night[len(night) // 2]["slot"]
hours = (night[-1]["slot"] - night[0]["slot"]) * 0.217 / 3600
TR = [o for o in U if o["set"] in ("hist", "fwd")]
NI = night
print(f"train (hist random + fwd run 1) {len(TR)} launches | test night {len(NI)} over {hours:.2f} h ({len(NI) / hours * 24:.0f} base launches/day)")


def first(o, fn, kmax=0):
    for j, z in enumerate(o["tr"]):
        if z[1] > kmax:
            return None
        if fn(o, j, z):
            return j
    return None


def cum_sol(o, j):
    return sum(z[4] for z in o["tr"][:j + 1] if z[3] == "O")


def n_out(o, j):
    return len({z[5] for z in o["tr"][:j + 1] if z[3] == "O"})


TRIG = {
    "create (base filter)": (lambda o: True, None),
    "create, Gate B": (lambda o: o["gateB"], None),
    "create, hindsight RACE (not tradable)": (lambda o: o["race"], None),
    "1st outside buy >=1 SOL": (lambda o: True, lambda o, j, z: z[3] == "O" and z[4] >= 1),
    "cum outside SOL >=2": (lambda o: True, lambda o, j, z: z[3] == "O" and cum_sol(o, j) >= 2),
    ">=3 outsiders & >=3 SOL": (lambda o: True, lambda o, j, z: z[3] == "O" and n_out(o, j) >= 3 and cum_sol(o, j) >= 3),
    "whale >=5 SOL": (lambda o: True, lambda o, j, z: z[3] == "O" and z[4] >= 5),
    "whale 3-10 SOL": (lambda o: True, lambda o, j, z: z[3] == "O" and 3 <= z[4] < 10),
    "4yFAz buys": (lambda o: True, lambda o, j, z: z[3] == "O" and z[9]),
}
DL = [1, 5, 10, 25, 50, 100]
print("\n== (1) DECAY: mean realistic PnL (2 SOL) vs landing delay after the signal, exit t1 / t3. train | NIGHT")
for nm, (pre, fn) in TRIG.items():
    for setn, S_ in (("train", TR), ("NIGHT", NI)):
        g = []
        for o in S_:
            if not pre(o):
                continue
            j = -1 if fn is None else first(o, fn)
            if j is None:
                continue
            g.append((o, j))
        cells = []
        for xn in ("t1", "t3"):
            c = []
            for d in DL:
                c.append(f"+{d}:{st.mean(sim(o, land_time(o, j, ('S', d)), EXITS[xn]) for o, j in g):+5.1%}")
            c.append(f"S1front:{st.mean(sim(o, land_time(o, j, ('S1', 0.0)), EXITS[xn]) for o, j in g):+5.1%}")
            c.append(f"S1mid:{st.mean(sim(o, land_time(o, j, ('S1', 0.5)), EXITS[xn]) for o, j in g):+5.1%}")
            cells.append(f"{xn} " + " ".join(c))
        print(f"   {nm:38} {setn:5} n={len(g):4} | " + " || ".join(cells))

print("\n== (2) RACE-AWARE EXIT on a zero-wait entry (land S+100 after the create, or S+1 mid): at t0+W check outside SOL seen since the create;"
      " >= Y -> hold to LONG, else sell at max(W, 500 ms). Fit on train, judged on night. 2 SOL")
LONG = {"t2": dict(T=2000), "t3": dict(T=3000), "t5": dict(T=5000), "t10": dict(T=10000), "trail0.8/40s": dict(T=40000, trail=0.8),
        "70%1s+trail0.8/40s": EXITS["70%1s+trail0.8/40s"]}
res = []
ntried = 0
for pren, pre in (("base", lambda o: True), ("gateB", lambda o: o["gateB"])):
    for lm in (("S", 100), ("S1", 0.5)):
        for W in (200, 400, 600):
            for Y in (1, 2, 3, 5):
                for ln, lx in LONG.items():
                    ntried += 1
                    out = {}
                    for setn, S_ in (("hist", [o for o in TR if o["set"] == "hist"]), ("fwd", [o for o in TR if o["set"] == "fwd"]), ("night", NI)):
                        v = []
                        for o in S_:
                            if not pre(o):
                                continue
                            t0 = land_time(o, -1, lm)
                            seen = sum(z[4] for z in o["tr"] if z[3] == "O" and z[0] <= t0 + W)
                            v.append(sim(o, t0, lx) if seen >= Y else sim(o, t0, dict(T=max(W, 500))))
                        out[setn] = stats(v)
                    res.append((min(out["hist"]["avg"], out["fwd"]["avg"]), pren, lm, W, Y, ln, out))
res.sort(key=lambda r: -r[0])
print(f"   rules tried {ntried}")
for r in res[:12]:
    print(f"   {r[1]:5} land {r[2]} W {r[3]} Y {r[4]} LONG {r[5]:18} | worst-train {r[0]:+.1%} | hist {fmt(r[6]['hist'])} | fwd {fmt(r[6]['fwd'])} | NIGHT {fmt(r[6]['night'])}")
for pren, pre in (("base", lambda o: True), ("gateB", lambda o: o["gateB"])):
    for lm in (("S", 100), ("S1", 0.5)):
        for xn in ("t0.5", "t1", "t3"):
            v = [sim(o, land_time(o, -1, lm), EXITS[xn]) for o in NI if pre(o)]
            print(f"   reference {pren:5} land {lm} plain {xn}: NIGHT {fmt(stats(v))}")

print("\n== (3) STRATEGY TABLE (NIGHT = test; train = hist random + fwd run 1). fires/day from the night rate. Blend = 0.4 x S+100 + 0.6 x S+1 mid.")
STRATS = [("Gate B zero-wait, sell +1 s", lambda o: o["gateB"], None, "t1"),
          ("Gate B zero-wait, sell +0.5 s", lambda o: o["gateB"], None, "t0.5"),
          ("base filter zero-wait, sell +1 s", lambda o: True, None, "t1"),
          ("whale >=5 SOL in S, sell +3 s", lambda o: True, lambda o, j, z: z[3] == "O" and z[4] >= 5, "t3"),
          ("whale >=5 SOL in S, sell +2 s", lambda o: True, lambda o, j, z: z[3] == "O" and z[4] >= 5, "t2"),
          (">=3 outsiders & >=3 SOL in S, sell +1 s", lambda o: True, lambda o, j, z: z[3] == "O" and n_out(o, j) >= 3 and cum_sol(o, j) >= 3, "t1"),
          ("cum outside SOL >=2 in S, sell +1 s", lambda o: True, lambda o, j, z: z[3] == "O" and cum_sol(o, j) >= 2, "t1"),
          ("4yFAz buys in S, sell +1 s", lambda o: True, lambda o, j, z: z[3] == "O" and z[9], "t1"),
          ("HINDSIGHT race, zero-wait, sell +1 s (not tradable)", lambda o: o["race"], None, "t1")]
for nm, pre, fn, xn in STRATS:
    print(f"\n-- {nm}")
    for lab, lm in (("land S+100", ("S", 100)), ("land S+25 (fast lane)", ("S", 25)), ("land S+1 front", ("S1", 0.0)), ("land S+1 mid", ("S1", 0.5)), ("BLEND 40/60", None)):
        for setn, S_ in (("train", TR), ("nightA", [o for o in NI if o["slot"] < mid]), ("nightB", [o for o in NI if o["slot"] >= mid]), ("NIGHT", NI)):
            g = []
            for o in S_:
                if not pre(o):
                    continue
                j = -1 if fn is None else first(o, fn)
                if j is None:
                    continue
                g.append((o, j))
            row = []
            for size in (2.0, 1.0):
                if lm is None:
                    v = [0.4 * sim(o, land_time(o, j, ("S", 100)), EXITS[xn], size) + 0.6 * sim(o, land_time(o, j, ("S1", 0.5)), EXITS[xn], size) for o, j in g]
                else:
                    v = [sim(o, land_time(o, j, lm), EXITS[xn], size) for o, j in g]
                row.append(stats(v))
            if setn == "NIGHT":
                fpd = len(g) / hours * 24
                print(f"   {lab:22} {setn:6} {fmt(row[0])} @2 | {fpd:5.0f}/day | SOL/day @2 {row[0]['avg'] * 2 * fpd:+7.1f} (ex3 {row[0]['ex3'] * 2 * fpd:+7.1f}) | @1 {row[1]['avg'] * fpd:+7.1f} (avg {row[1]['avg']:+.1%})")
            else:
                print(f"   {lab:22} {setn:6} {fmt(row[0])} @2 | @1 avg {row[1]['avg']:+.1%}")

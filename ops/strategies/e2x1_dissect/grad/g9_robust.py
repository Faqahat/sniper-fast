#!/usr/bin/env python3
"""grad agent, step 9: robustness of the train-chosen rules — every day (10-23 evening .. 10-28), neighbours in V / flow / exit,
cost +2 mSOL, concentration (without the top-5 trades), pool-open whale share."""
import pickle, numpy as np
G = "/home/moiz/sniper-data/e2x1_dissect/grad"
D = pickle.load(open(G + "/sim.pkl", "rb")); R = D["R"]; EX = D["EXITS"]
po = {r["mint"]: r for r in pickle.load(open(G + "/pool_open.pkl", "rb"))}
ok = [r for r in R if r.get("res") is not None and not r["edge"] and not (r["grad"] and not r["has_mig"])]
DAYS = ["10-23", "10-24", "10-25", "10-26", "10-27", "10-28"]; TR = DAYS[1:4]; TE = DAYS[4:]
def rows(V, S, X): return [r for r in ok if r["V"] == V and r["S"] == S and r["flow10"] >= X]
def line(name, rr, xi):
    s = []
    for d in DAYS:
        a = [r for r in rr if r["day"] == d]
        s.append(f"{d[3:]}:{sum(r['res'][xi] for r in a):+6.2f}({sum(r['fill'] for r in a):4.0f})")
    tr = sum(r["res"][xi] for r in rr if r["day"] in TR) / 3; te = sum(r["res"][xi] for r in rr if r["day"] in TE) / 2
    print(f"{name:44s} train {tr:+6.2f}/d test {te:+6.2f}/d | " + " ".join(s))
xA = EX.index((100, 0.2, 120)); xB = EX.index((48, 0.2, 120)); xC = EX.index((100, 0.2, 1800))
print("days: SOL (entries); 10-23 = evening only, 10-28 = to ~20:35 PKT")
line("BASE V105 S0.5 mig+100 SL20 TO1800 (train pick)", rows(105, 0.5, -1e9), xC)
line("SEL V105 S1 flow>=20 mig+100 SL20 TO120 (pick)", rows(105, 1.0, 20), xA)
for X in (0, 5, 10, 20, 30, 40):
    line(f"  V105 S1 flow>={X} mig+100 SL20 TO120", rows(105, 1.0, X), xA)
for V in (90, 95, 100):
    line(f"  V{V} S1 flow>=20 mig+100 SL20 TO120", rows(V, 1.0, 20), xA)
for n in (5, 20, 48, 200):
    line(f"  V105 S1 flow>=20 mig+{n} SL20 TO120", rows(105, 1.0, 20), EX.index((n, 0.2, 120)))
line("  V105 S0.5 flow>=20 mig+100 SL20 TO120", rows(105, 0.5, 20), xA)
sel = rows(105, 1.0, 20)
for ds, nm in ((TR, "train"), (TE, "test")):
    a = [r for r in sel if r["day"] in ds]; p = np.array([r["res"][xA] for r in a]); srt = np.sort(p)[::-1]
    g = np.array([r["grad"] for r in a]); wh = np.array([po.get(r["mint"], {}).get("buy_sol5", 0) > 20 for r in a])
    c2 = sum(r["res"][xA] - 0.002 * r["fill"] for r in a)
    print(f"{nm}: total {p.sum():+.2f} over {len(ds)} d | w/o top-5 trades {srt[5:].sum():+.2f} | +2 mSOL cost/entry {c2:+.2f} | "
          f"graduated {p[g].sum():+.2f} (pool-open whale >20 SOL: {int((g & wh).sum())} picks {p[g & wh].sum():+.2f}) | failed {p[~g].sum():+.2f} | entries {sum(r['fill'] for r in a):.0f}")

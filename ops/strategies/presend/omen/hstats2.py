import pickle, collections, numpy as np
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen"
Z = pickle.load(open(f"{W}/hab.pkl", "rb")); P = Z["P"]
def elig(p): return (not p["creator"]) and (not p["insider"]) and p["age"] > 0 and p["vsol"] < 100e9
EP = [p for p in P if p["D"] >= 2 and elig(p)]
def hab(f, n=10, iqr=5): return f["n"] >= n and f["iqr"] <= iqr and f["med"] <= 150
H = [p for p in EP if hab(p["f"])]
c = collections.Counter(int(min(p["f"]["med"], 40)) for p in H); print("habitual med dist:", sorted(c.items()))
def bd(p, a, b): return "bd" in p and a <= p["bd"] - p["s"] <= b
# own big dump (>=1 SOL, >=12%) in 1..10 after open, by pct band and habit
for lo, hi in ((2, 3), (3, 4), (4, 6), (6, 100)):
    S = [p for p in EP if lo <= p["pct"] < hi and p["D"] <= 4]
    r = np.mean([bd(p, 1, 10) for p in S])
    Hh = [p for p in S if hab(p["f"]) and 1 <= p["f"]["med"] <= 10]
    r2 = np.mean([bd(p, 1, 10) for p in Hh]) if Hh else 0
    r3 = np.mean([bd(p, max(1, int(p["f"]["med"]) - 2), int(p["f"]["med"]) + 2) for p in Hh]) if Hh else 0
    U = [p for p in S if p["f"]["n"] < 3]
    NH = [p for p in S if p["f"]["n"] >= 10 and not (hab(p["f"]) and 1 <= p["f"]["med"] <= 10)]
    print(f"TRAIN pct {lo}-{hi}: n/day {len(S)/3:.0f}; own big dump in 1..10: all {r:.3f}; habitual med 1-10 {len(Hh)/3:.0f}/day -> {r2:.3f} (in med+-2: {r3:.3f}); unknown(<3 prior) {len(U)/3:.0f}/day {np.mean([bd(p,1,10) for p in U]):.3f}; known non-habit {len(NH)/3:.0f}/day {np.mean([bd(p,1,10) for p in NH]):.3f}")
# pbig30 as predictor (the p of past positions dumped big within 30)
for lo in (2, 6):
    S = [p for p in EP if p["pct"] >= lo and p["D"] <= 4 and p["f"]["n"] >= 5]
    for q0, q1 in ((0, .1), (.1, .3), (.3, .5), (.5, .7), (.7, .9), (.9, 1.01)):
        T = [p for p in S if q0 <= p["f"]["pbig30"] < q1]
        if T: print(f"  pct>={lo} n>=5 pbig30 {q0}-{q1}: {len(T)/3:.0f}/day bd1-10 {np.mean([bd(p,1,10) for p in T]):.3f} bd1-30 {np.mean([bd(p,1,30) for p in T]):.3f}")

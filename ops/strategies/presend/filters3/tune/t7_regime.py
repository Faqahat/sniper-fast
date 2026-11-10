#!/usr/bin/env python3
"""TUNE t7: regime-gated holder rule: apply a LOG holder rule as a block only while the rolling mean of our last N KEPT realized trades
(known before the arm, record order; carried across runs) is below M mSOL. Idea: the flagged trades are ~10-20 mSOL worse than average in
every period, so blocking them pays only when the average trade is weak. Fit N, M on DEV; check VALx / VAL / HOLD."""
import sys, pickle, collections, itertools
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/it/sniper-data/filters3/tune/pos_all.pkl", "rb"))
A0, A1 = 1793590164e9 - 60e9, 1793590555e9 + 60e9
for r in P:
    r["attk"] = r["run"] == "r42" and A0 <= r["t"] <= A1
    a = T.load(r["run"])["arms"].get(r["k"], {}); r["arm_seq"] = a.get("_seq", r["seq"])
SEG = {"DEV": lambda r: r["per"] == "DEV" and r["run"] in ("r40", "r41", "r42"), "VALx": lambda r: r["per"] == "VAL" and not r["attk"],
       "VAL": lambda r: r["per"] == "VAL", "HOLD": lambda r: r["per"] == "HOLD"}
def sim(rule, N, M):
    blocked = set(); hist = collections.deque(maxlen=N)
    for run in T.RUNS:
        R = [r for r in P if r["run"] == run]
        evs = sorted([(r["arm_seq"], 0, i) for i, r in enumerate(R)] + [(r["seq"], 1, i) for i, r in enumerate(R)])
        for s, typ, i in evs:
            r = R[i]
            if typ == 0:
                on = len(hist) >= N and 1000 * sum(hist) / len(hist) < M
                if on and rule(r): blocked.add((run, r["k"]))
            elif (run, r["k"]) not in blocked: hist.append(r["pnl"])
    return blocked
def sc(B):
    out = []
    for sn, sf in SEG.items():
        v = [r["pnl"] for r in P if sf(r) and (r["run"], r["k"]) in B]
        out.append(f"{sn} {len(v):3d} {-sum(v):+6.3f} w5 {T.wo_top(v):+6.3f}")
    return " | ".join(out)
for rn, rule in (("group", lambda r: r["grp"]), ("safe", lambda r: r["st"]), ("group T2", lambda r: r["grp"] and r["kind"] == "t2")):
    print(f"{rn:9s} always              | " + sc({(r["run"], r["k"]) for r in P if rule(r)}))
    for N, M in itertools.product((30, 50, 100, 200), (0, 5, 10)):
        print(f"{rn:9s} N {N:3d} mean < {M:2d} mSOL | " + sc(sim(rule, N, M)))

#!/usr/bin/env python3
"""e5: robustness of the earlier timer exit. Model-vs-model: for each "time-ms" position the sell is replayed at the real decision
time AND at the shifted one with the SAME set of landing delays (the period's L deciles 10..90%, each = one sample), so both sides
carry the model's errors equally. Also by kind (T2 / re-arm)."""
import sys, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/obsstrat")
import tlib
HRS = {"DEV": 74.35, "VAL": 20.61}
P = [(d, tlib.Pos(d)) for d in tlib.load()]
P = [(d, p) for d, p in P if p.ok and p.why == "time-ms"]
Ls = collections.defaultdict(list)
for d, p in P: Ls[d["per"]].append(p.L)
Q = {per: [sorted(v)[int(len(v) * q / 10)] for q in range(1, 10)] for per, v in Ls.items()}
print("L deciles ms:", {k: [round(x / 1e6) for x in v] for k, v in Q.items()})
SH = (-125, -100, -75, -50, -25, 50)
R = collections.defaultdict(lambda: collections.defaultdict(float)); N = collections.Counter()
for d, p in P:
    per = d["per"]; N[per] += 1
    for L in Q[per]:
        b0, _ = p.proceeds_at(p.T, L)
        for s in SH:
            T = max(p.T + s * 1e6, p.tfill + 1e6)
            if T + L > p.tape_end_t(): T = p.tape_end_t() - L
            cf, _ = p.proceeds_at(T, L)
            dd = (cf - b0) * (1 - tlib.FEE_SELL) / 1e9 / len(Q[per])
            R[per][s] += dd; R[per + "/" + d["kind"]][s] += dd
for k in sorted(R):
    per = k.split("/")[0]
    print(f"{k:10s} " + " | ".join(f"{200+s}ms {R[k][s]:+.3f} ({R[k][s]/HRS[per]*24:+.2f}/d)" for s in SH))

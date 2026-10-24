# exploratory variants (not frozen) on the same walk-forward harness as exp.py
import sys, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import exp
S9 = exp.S9
g = lambda st: exp.gate_ok(st)
good = lambda st: len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02
V = {
  "S4G (frozen)": lambda st: 0.5 if exp.listed(st, S9) and g(st) else 0,
  "S4G + AUTO (own-history deployers outside the list)": lambda st: 0.5 if ((exp.listed(st, S9) and g(st)) or good(st)) else 0,
  "S4G + AUTO, size 1.0 on good": lambda st: (1.0 if good(st) else 0.5) if ((exp.listed(st, S9) and g(st)) or good(st)) else 0,
  "S4G stricter gate (>=2 fills, avg < 0 -> skip)": lambda st: 0.5 if exp.listed(st, S9) and exp.gate_ok(st, kmin=2) else 0,
  "S4G gate threshold avg < +0.01": lambda st: 0.5 if exp.listed(st, S9) and exp.gate_ok(st, thr=0.01) else 0,
  "S4 list k>=1 + gate": lambda st: 0.5 if exp.listed(st, S9, k=1) and g(st) else 0,
  "S4 list rate>=5% + gate": lambda st: 0.5 if exp.listed(st, S9, rate=0.05) and g(st) else 0,
  "S4 list rate>=20% + gate": lambda st: 0.5 if exp.listed(st, S9, rate=0.20) and g(st) else 0,
}
for Lm in (75, 45):
    print(f"\n=== {Lm} ms ===")
    for n, f in V.items(): exp.run(f, Lm, n)

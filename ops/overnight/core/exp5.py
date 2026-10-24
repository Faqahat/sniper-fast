# engine-friendly variants (one fixed size per run): S4G only on big launches at 1.0 SOL, or everything at 1.0 SOL
import sys, json, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import exp
exp.R = json.load(open("allres_static_0034.json"))
S9 = exp.S9; g = lambda st: exp.gate_ok(st)
V = {
  "S4G all at 0.5": lambda st: 0.5 if exp.listed(st, S9) and g(st) else 0,
  "S4G all at 1.0": lambda st: 1.0 if exp.listed(st, S9) and g(st) else 0,
  "S4G only MC>=36, 1.0": lambda st: 1.0 if exp.listed(st, S9) and g(st) and st["r"]["mc_b"] >= 36 else 0,
  "S4G only MC>=36, 0.5": lambda st: 0.5 if exp.listed(st, S9) and g(st) and st["r"]["mc_b"] >= 36 else 0,
  "S4G only MC<36, 0.5": lambda st: 0.5 if exp.listed(st, S9) and g(st) and st["r"]["mc_b"] < 36 else 0,
}
for Lm in (75, 45):
    print(f"\n=== {Lm} ms ===")
    for n, f in V.items(): exp.run(f, Lm, n)

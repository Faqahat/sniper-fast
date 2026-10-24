# dKMjeG-style sizing for S4G: 1.0 SOL when the dev's own buy (or market cap after the bundle) is big, else 0.5
import sys, json, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import exp
exp.R = json.load(open("allres_static_0034.json"))
S9 = exp.S9; g = lambda st: exp.gate_ok(st)
good = lambda st: len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02
V = {
  "S4G 0.5 flat": lambda st: 0.5 if exp.listed(st, S9) and g(st) else 0,
  "S4G + 1.0 if dev buy >= 3 SOL": lambda st: (1.0 if st["r"]["dev"] >= 3 else 0.5) if exp.listed(st, S9) and g(st) else 0,
  "S4G + 1.0 if MC after bundle >= 36 SOL": lambda st: (1.0 if st["r"]["mc_b"] >= 36 else 0.5) if exp.listed(st, S9) and g(st) else 0,
  "S4G + 1.0 if good own history (S4GS)": lambda st: (1.0 if good(st) else 0.5) if exp.listed(st, S9) and g(st) else 0,
  "S4G + 1.0 if good history OR MC>=36": lambda st: (1.0 if (good(st) or st["r"]["mc_b"] >= 36) else 0.5) if exp.listed(st, S9) and g(st) else 0,
  "S4G + 0.25 if MC < 32 else 0.5": lambda st: (0.25 if st["r"]["mc_b"] < 32 else 0.5) if exp.listed(st, S9) and g(st) else 0,
}
for Lm in (75, 45):
    print(f"\n=== {Lm} ms (total SOL; R1 old proxy / R2 replay) ===")
    for n, f in V.items(): exp.run(f, Lm, n)

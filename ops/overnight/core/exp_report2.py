# saves the sizing variants (frozen 02:46) for the report, computed on the static outcome table (data to 00:34)
import sys, json, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import exp
exp.R = json.load(open("allres_static_0034.json"))
S9 = exp.S9; g = lambda st: exp.gate_ok(st); good = lambda st: len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02
V = {"S4G_1SOL": lambda st: 1.0 if exp.listed(st, S9) and g(st) else 0,
     "S4GM": lambda st: (1.0 if st["r"]["mc_b"] >= 36 else 0.5) if exp.listed(st, S9) and g(st) else 0,
     "S4GSM": lambda st: (1.0 if (good(st) or st["r"]["mc_b"] >= 36) else 0.5) if exp.listed(st, S9) and g(st) else 0,
     "S4G_BIG_ONLY": lambda st: 1.0 if exp.listed(st, S9) and g(st) and st["r"]["mc_b"] >= 36 else 0}
out = {}
for Lm in (75, 45):
    for n, f in V.items(): out.setdefault(n, {})[str(Lm)] = exp.run(f, Lm, n, verbose=False)
json.dump(out, open("/home/moiz/sniper/ops/overnight/report/exp2.json", "w")); print("saved")

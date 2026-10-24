# runs the frozen exp.py strategies (imported, unchanged) and saves the walk-forward results for the report
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import exp
out = {}
for Lm in (75, 45):
    for n, f in exp.STRATS.items():
        out.setdefault(n, {})[str(Lm)] = exp.run(f, Lm, n, verbose=False)
json.dump(out, open("/home/moiz/sniper/ops/overnight/report/exp.json", "w"))
print("saved", len(out))

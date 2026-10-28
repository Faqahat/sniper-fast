import sys, json
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen/code")
from omrep import *
DAYS = [Day(D, "train") for D in (2, 3, 4)]
V = [k for k in DAYS[0].out if k != "base"]
res = {}
for v in V:
    a = boot(DAYS, delta_fn(v), n=400); c = boot(DAYS, delta_fn(v, key=K65c), n=400)
    per = [boot([d], delta_fn(v, key=K65c), n=1)[0] for d in DAYS]
    res[v] = (a, c, per)
print("| variant | TRAIN Δ raw | TRAIN Δ −20% followers | per day −20% |")
for v in sorted(V, key=lambda v: -res[v][1][0]):
    a, c, per = res[v]; print(f"| {v} | {fmt(*a)} | {fmt(*c)} | " + " / ".join(f"{x:+.2f}" for x in per) + " |")
best = {}
for X in (2, 3, 4, 6):
    cand = [v for v in V if v.startswith(f"C{X}_")]; b = max(cand, key=lambda v: res[v][1][0]); best[X] = b
print("TRAIN-best per X:", best)
json.dump(best, open(f"{W}/train_best.json", "w"))

#!/usr/bin/env python3
# READ-ONLY. Owner's criterion: TOTAL GAIN per day. Rank every pre-registered candidate on the BLIND overnight run by
# expected SOL/day = mean realistic PnL x fires/day x size, at size 1 and 2 SOL, landing behind <= 100 txs (today) and
# <= 25 txs (after landing fixes), with a bootstrap 90% CI. Exits are the ones frozen in EXIT_FREEZE.json (03:22 UTC) /
# PREREG_v2.json (20:44 UTC) before any overnight outcome was read; nothing is refitted here.
# usage: eval_rank.py [tag] (default night)
import sys, json, random, statistics as st
sys.path.insert(0, "/root/race")
from hc_search import sim, EXITS, hostbad, C
from fwdrows import build
tag = sys.argv[1] if len(sys.argv) > 1 else "night"
F = [o for o in build(f"/root/race/paper_{tag}.log", f"/root/race/{tag}_onchain.jsonl", f"/root/race/paths_{tag}.jsonl", verbose=False)
     if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
days = (F[-1]["slot"] - F[0]["slot"]) * 0.217 / 86400
fz = json.load(open("/root/race/EXIT_FREEZE.json"))["gates"]
pre = json.load(open("/root/race/PREREG_v2.json"))["prereg"]
G = {"Gate B": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2 and r["n_len"] <= 12,
     "Gate B strict (bundle>=3)": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 3 and r["n_len"] <= 12,
     "Gate B no-name (dev>=3 & bundle>=2)": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2,
     "FIX base": lambda r: True}
for k, p in enumerate(pre):
    G[f"PREREG_v2 #{k + 1}"] = (lambda r, rule=p["rule"]: all(C[c](r) for c in rule))
desc = {f"PREREG_v2 #{k + 1}": " & ".join(p["rule"]) for k, p in enumerate(pre)}


def boot(v, n=3000):
    rnd = random.Random(11)
    m = sorted(st.mean(rnd.choices(v, k=len(v))) for _ in range(n))
    return m[int(.05 * n)], m[int(.95 * n)]


res = []
print(f"BLIND run '{tag}': {len(F)} base launches over {days * 24:.2f} h. SOL/day = mean x fires/day x size. 90% CI by bootstrap.")
for gn, fn in G.items():
    g = [o for o in F if fn(o)]
    if len(g) < 5:
        continue
    fpd = len(g) / days
    xs = [("frozen", fz[gn]["exit"]), ("runner", fz[gn]["best_runner_exit"]), ("1s", "time 1s")]
    for xl, xn in xs:
        for d in (100, 25):
            for size in (1.0, 2.0):
                v = [sim(o, EXITS[xn], d_land=d, size=size) for o in g]
                lo, hi = boot(v)
                res.append((gn, xl, xn, d, size, len(g), fpd, st.mean(v), lo, hi, st.median(v), sum(x > 0 for x in v) / len(v)))
print(f"\n{'candidate':38} {'exit':6} {'land':5} {'size':4} | {'n':>4} {'fires/day':>9} | {'mean':>6} [90% CI]        | SOL/day [90% CI]          | median  win")
for r in sorted(res, key=lambda z: -(z[7] * z[6] * z[4]) if (z[3] == 100 and z[4] == 2.0) else 0):
    pass
order = sorted({(r[0], r[1]) for r in res}, key=lambda k: -max(x[7] * x[6] * x[4] for x in res if (x[0], x[1]) == k and x[3] == 100 and x[4] == 2.0))
for k in order:
    for r in [x for x in res if (x[0], x[1]) == k]:
        gn, xl, xn, d, size, n, fpd, m, lo, hi, med, win = r
        print(f"{gn[:38]:38} {xl:6} d{d:<4} {size:3.0f} | {n:4} {fpd:9.0f} | {m:+6.1%} [{lo:+5.1%},{hi:+5.1%}] | {m * fpd * size:+7.1f} [{lo * fpd * size:+6.1f},{hi * fpd * size:+6.1f}] | {med:+5.1%} {win:4.0%}")
    print(f"{'':38} exit = {[x for x in res if (x[0], x[1]) == k][0][2]}" + (f" | rule: {desc[k[0]]}" if k[0] in desc else ""))

#!/usr/bin/env python3
# READ-ONLY. FINAL out-of-sample judgement of the gates frozen BEFORE the overnight run's outcomes were looked at:
#   FROZEN_GATE.txt (20:12 UTC)  : Gate B, exits 1.6 s (= the "3 s" of the then-400ms-scaled sim) and 0.54 s ("1 s"), plus real 1 s / 3 s
#   PREREG_v2.json  (20:44 UTC)  : the top 5 multi-period rules with their exits
# on the overnight PAPER run (a census of every base launch, gate decisions + shadow-tracked rejects), REALISTIC model
# (hc_search.sim: 2 SOL, land S behind every trade <= 100 txs, x1.03, own impact, pump 1.25%/side, 0.009 SOL buy prio).
# Also: per-hour rates (217 ms slots), contested rate, 4yFAz overlap, bootstrap 90% CI of the mean, SOL/day at 2 SOL,
# landing sensitivity, and the same numbers per 2-hour block (stability).
# usage: eval_night.py [tag]   (default night)
import sys, json, random, statistics as st, math
sys.path.insert(0, "/root/race")
from hc_search import sim, stats, fmt, hostbad, C, EXITS, entry_vsol
from fwdrows import build

tag = sys.argv[1] if len(sys.argv) > 1 else "night"
F = [o for o in build(f"/root/race/paper_{tag}.log", f"/root/race/{tag}_onchain.jsonl", f"/root/race/paths_{tag}.jsonl")
     if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
hours = (F[-1]["slot"] - F[0]["slot"]) * 0.217 / 3600
RACE = lambda o: o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3
pre = json.load(open("/root/race/PREREG_v2.json"))["prereg"]
GATES = [("FIX base filter (no gate)", lambda o: True, ["time 1s", "time 3s"]),
         ("OLD filter (sized dev 0.5-8)", lambda o: 0.5 <= o["dev_sized"] <= 8, ["time 1s"]),
         ("FROZEN Gate B (engine decision)", lambda o: o["fired"], ["T543", "T1630", "time 1s", "time 1.5s", "time 3s"]),
         ("Gate B (recomputed from chain bundle)", lambda o: o["dev_sol"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12, ["time 1s", "time 1.5s", "time 3s"]),
         ("Gate B strict (bundle >= 3 tx)", lambda o: o["dev_sol"] >= 3 and o["glued"] >= 3 and o["n_len"] <= 12, ["time 1s", "time 3s"])]
for k, p in enumerate(pre):
    GATES.append((f"PREREG_v2 #{k + 1}: " + " & ".join(p["rule"]), (lambda o, rule=p["rule"]: all(C[c](o) for c in rule)), [p["exit"], "time 1s"]))
GATES.append(("stream race gate (>=2 SOL outside in 100 ms; engine obs)", lambda o: sum(x[1] for x in o["eng_outs"] if x[0] <= 100) >= 2.0, ["time 1s"]))
GATES.append(("4yFAz bought (hindsight)", lambda o: o["his"], ["time 1s", "time 3s"]))
GATES.append(("HINDSIGHT race", RACE, ["time 1s", "time 3s"]))
EXX = dict(EXITS)
EXX["T543"] = dict(legs=[], T=543)
EXX["T1630"] = dict(legs=[], T=1630)


def boot(v, n=2000):
    if len(v) < 5:
        return (float("nan"), float("nan"))
    rnd = random.Random(7)
    ms = sorted(st.mean(rnd.choices(v, k=len(v))) for _ in range(n))
    return ms[int(0.05 * n)], ms[int(0.95 * n)]


print(f"OVERNIGHT run '{tag}': {len(F)} scored base launches over {hours:.2f} h ({len(F) / hours:.0f}/h) | realistic model, 2 SOL")
for gn, fn, exits in GATES:
    g = [o for o in F if fn(o)]
    if not g:
        print(f"\n== {gn}: n=0")
        continue
    wait = 100 if gn.startswith("stream") else 0
    print(f"\n== {gn}: n={len(g)} ({len(g) / hours:.1f}/h, {len(g) / hours * 24:.0f}/day) | contested {sum(RACE(o) for o in g) / len(g):.0%} | "
          f"4yFAz {sum(o['his'] for o in g)} | entry/floor med {st.median((entry_vsol(o, 100 + int(wait / o['ms_per_tx'])) / o['base']) ** 2 for o in g):.2f}x")
    for xn in exits:
        v = [sim(o, EXX[xn], d_land=100 + int(wait / o["ms_per_tx"])) for o in g]
        lo, hi = boot(v)
        s = stats(v)
        pdy = len(g) / hours * 24
        print(f"   exit {xn:22} {fmt(s)} | 90% CI of mean [{lo:+.1%}, {hi:+.1%}] | SOL/day @2 SOL {s['avg'] * 2 * pdy:+.0f} [{lo * 2 * pdy:+.0f}, {hi * 2 * pdy:+.0f}]")
    xn = exits[0]
    print("   landing (" + xn + "): " + "  ".join(f"d{d}: {stats([sim(o, EXX[xn], d_land=d + int(wait / o['ms_per_tx'])) for o in g])['avg']:+.1%}" for d in (5, 25, 50, 100, 150))
          + f"  S+1: {stats([sim(o, EXX[xn], land_s1=True) for o in g])['avg']:+.1%}")
    # stability: 2-hour blocks
    blocks = {}
    for o in g:
        blocks.setdefault(int((o["slot"] - F[0]["slot"]) * 0.217 / 7200), []).append(sim(o, EXX[xn], d_land=100 + int(wait / o["ms_per_tx"])))
    print("   per 2-h block (" + xn + "): " + "  ".join(f"[{b * 2}-{b * 2 + 2}h] n={len(v)} {st.mean(v):+.1%}" for b, v in sorted(blocks.items())))

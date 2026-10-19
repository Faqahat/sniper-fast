#!/usr/bin/env python3
# READ-ONLY. REALISTIC scorer for a race-gate PAPER run (use this, not the engine's own "PAPER-TRADE RESULT", which enters
# at the floor). Needs: the paper log (with --race-log/--race-gate and ideally --race-track-rejects), the on-chain cache from
#   python3 /root/race/onchain.py /root/race/<tag>_onchain.jsonl 6 /root/race/paper_<tag>.log
# and the engine's --dump-paths file. Prints, for FIRED / REJECTED / ALL base launches: fires per hour, contested (race) rate,
# 4yFAz overlap, and the realistic return per trade (2 SOL, land in S behind every trade at offset <= 100 txs, entry x1.03,
# own impact, pump fee 1.25%/side, 0.009 SOL buy priority, 0.001 SOL/sell) for 1 s / 1.5 s / 3 s exits, plus landing
# sensitivity and SOL/day at 2 SOL.
# usage: score_run.py <tag> [size_sol]
import sys, statistics as st, math
sys.path.insert(0, "/root/race")
import hc_search
from hc_search import sim, stats, fmt, hostbad
from fwdrows import build

tag = sys.argv[1]
size = float(sys.argv[2]) if len(sys.argv) > 2 else hc_search.SIZE
_sim = sim
sim = lambda o, ex, **kw: _sim(o, ex, size=size, **kw)
F = [o for o in build(f"/root/race/paper_{tag}.log", f"/root/race/{tag}_onchain.jsonl", f"/root/race/paths_{tag}.jsonl")
     if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
if not F:
    sys.exit("no scored launches")
hours = max(1e-9, (F[-1]["slot"] - F[0]["slot"]) * 0.217 / 3600)   # 217 ms per slot (measured)
RACE = lambda o: o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3
EX = {"sell at +1 s": dict(legs=[], T=1000), "sell at +1.5 s": dict(legs=[], T=1500), "sell at +3 s": dict(legs=[], T=3000)}
print(f"run '{tag}': {len(F)} scored base launches over ~{hours:.2f} h (slot span) | size {size} SOL | realistic model: land S @<=100 txs, x1.03, fees, 0.009 SOL prio")
groups = [("FIRED by the gate", [o for o in F if o["fired"]]), ("REJECTED (shadow)", [o for o in F if not o["fired"]]), ("ALL base launches", F)]
for gn, g in groups:
    if not g:
        print(f"\n== {gn}: n=0")
        continue
    print(f"\n== {gn}: n={len(g)} ({len(g) / hours:.1f}/h) | contested (race) {sum(RACE(o) for o in g) / len(g):.0%} | "
          f">=2 outsiders S+S1 {sum(o['out01_nx'] >= 2 for o in g) / len(g):.0%} | 4yFAz bought {sum(o['his'] for o in g)}")
    for xn, ex in EX.items():
        s = stats([sim(o, ex) for o in g])
        se = (st.pstdev([sim(o, ex) for o in g]) / math.sqrt(len(g))) if len(g) > 1 else float("nan")
        per_day = len(g) / hours * 24
        print(f"   {xn:15} {fmt(s)} (+-{se:.1%} s.e.) -> {s['avg'] * size * per_day:+.1f} SOL/day at {per_day:.0f} trades/day "
              f"(ex-top3 {s['ex3'] * size * per_day:+.1f})")
    xn = "sell at +1 s"
    print("   landing sensitivity (" + xn + "): " + "  ".join(
        f"d{d}: {stats([sim(o, EX[xn], d_land=d) for o in g])['avg']:+.1%}" for d in (5, 25, 50, 100, 150))
          + f"  S+1: {stats([sim(o, EX[xn], land_s1=True) for o in g])['avg']:+.1%}")

#!/usr/bin/env python3
"""REARM step 11 (read-only; G2): landing stress. The same configs replayed with re-arm attempts landing 20 / 40 ms later than the
live T2 donors (tags rl20 / rl40: battleground slots may be harder to land in) and with EVERY attempt 20 ms later (gl20, base too).
ADDED model / cal per day (INFERRED). Also the draw spread (tag dr3: 3 landing draws of the chosen config). Out: r11.txt"""
import sys, os, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r8_report as R8
import dv8lib as L

OUT = R8.OUT
CF = ["any:20:30:8:2", "any:10:30:4:2", "0.02:50:120:2:0"]
days = [0, 1, 2, 3, 4, 5]
Lo = []
def P(s=""): print(s, flush=True); Lo.append(s)
P("# Landing stress (ADDED vs base; model / cal 0.81; SOL). no lag = tags g2/h2; rl20/rl40 = re-arm attempts +20/+40 ms; gl20 = every attempt +20 ms (base too)")
for c in CF:
    P(f"\n## {c}")
    P("| Day | no lag | re +20 ms | re +40 ms | all +20 ms | re fills no lag / +20 / +40 |")
    P("|---|---|---|---|---|---|")
    S = collections.defaultdict(float)
    for d in days:
        cells = []; fills = []
        for tags in (["g2", "h2"], ["rl20"], ["rl40"], ["gl20"]):
            r = R8.load_day(d, tags)
            if r is None or c not in r: cells.append("n/a"); fills.append("n/a"); continue
            m = R8.added(r, c)["net"]; k = R8.added(r, c, lvl="cal")["net"]
            cells.append(f"{m:+.2f} / {k:+.2f}"); S[tags[0] + "m"] += m; S[tags[0] + "c"] += k
            fills.append(str(R8.tot(r[c], kind="re")["f"]))
        P(f"| {L.day_name(d)} | " + " | ".join(cells) + f" | {fills[0]} / {fills[1]} / {fills[2]} |")
    P(f"| **Sum** | {S['g2m']:+.2f} / {S['g2c']:+.2f} | {S['rl20m']:+.2f} / {S['rl20c']:+.2f} | {S['rl40m']:+.2f} / {S['rl40c']:+.2f} | {S['gl20m']:+.2f} / {S['gl20c']:+.2f} | |")
# draw spread
P("\n## Landing draw spread of any:20:30:8:2 (tag dr3: draws 0..2, ADDED model)")
P("| Day | draw 0 | draw 1 | draw 2 |")
P("|---|---|---|---|")
for d in days + [6]:
    fn = f"{OUT}/res_D{d}_dr3.pkl"
    if not os.path.exists(fn): continue
    Z = pickle.load(open(fn, "rb"))["out"]
    v = []
    for i in range(len(Z["base"])):
        res = {"base": Z["base"][i], CF[0]: Z[CF[0]][i]}
        v.append(R8.added(res, CF[0])["net"])
    P(f"| {L.day_name(d)} | " + " | ".join(f"{x:+.2f}" for x in v) + " |")
open(f"{OUT}/r11.txt", "w").write("\n".join(Lo) + "\n")

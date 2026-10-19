#!/usr/bin/env python3
# READ-ONLY. whale >=5 SOL in S: every event, bootstrap CI, threshold sensitivity.
import sys, random, statistics as st
sys.path.insert(0, "/root/racedeep")
from rdlib import load, pf, sim, land_time, EXITS, stats, fmt
U = [o for o in load() if o["in_rand"]]
def wj(o, lo, kmax=0):
    for j, z in enumerate(o["tr"]):
        if z[1] > kmax: return None
        if z[3] == "O" and z[4] >= lo: return j
    return None
ev = []
for o in U:
    j = wj(o, 5)
    if j is None: continue
    z = o["tr"][j]
    a = sim(o, land_time(o, j, ("S", 100)), EXITS["t3"]); b = sim(o, land_time(o, j, ("S1", 0.5)), EXITS["t3"]); c = sim(o, land_time(o, j, ("S", 25)), EXITS["t3"])
    inS = z[2] + 100 <= o["rem"]
    ev.append((o["set"], o["slot"], o["mint"][:8], z[5][:8], z[4], z[2], o["rem"], inS, z[6] / 1e6, z[7], pf(o, z[0] + 1e-6), o["race"], c, a, b, o["dev"], o["glued"]))
ev.sort(key=lambda e: e[1])
print("set   slot       mint     whale    SOL   d   rem  S+100fits cuM   tip   pf@whale race | t3: S+25 / S+100 / S1mid | dev glued")
for e in ev:
    print(f"{e[0]:5} {e[1]} {e[2]} {e[3]} {e[4]:5.1f} {e[5]:4} {e[6]:4} {str(e[7]):5} {e[8]:7.1f} {e[9]:.3f} {e[10]:5.2f}x {str(e[11]):5} | {e[12]:+6.1%} {e[13]:+6.1%} {e[14]:+6.1%} | {e[15]:.2f} {e[16]}")
def boot(v, n=4000):
    r = random.Random(1); m = sorted(st.mean(r.choices(v, k=len(v))) for _ in range(n)); return m[int(.05*n)], m[int(.95*n)]
for setn in ("hist+fwd", "night"):
    g = [e for e in ev if (e[0] == "night") == (setn == "night")]
    for k, nm in ((12, "S+25"), (13, "S+100"), (14, "S1 mid")):
        v = [e[k] for e in g]
        lo, hi = boot(v)
        print(f"{setn:8} {nm:6} {fmt(stats(v))} 90% CI [{lo:+.1%}, {hi:+.1%}]")
    v = [0.4 * e[13] + 0.6 * e[14] for e in g]; lo, hi = boot(v)
    print(f"{setn:8} blend  {fmt(stats(v))} 90% CI [{lo:+.1%}, {hi:+.1%}]")
print("\nthreshold sensitivity, all periods pooled (t3): whale >= Y in S")
for Y in (4, 4.5, 5, 6, 7, 8):
    g = [(o, wj(o, Y)) for o in U]; g = [(o, j) for o, j in g if j is not None]
    for setn in ("train", "night"):
        h = [(o, j) for o, j in g if (o["set"] == "night") == (setn == "night")]
        a = [sim(o, land_time(o, j, ("S", 100)), EXITS["t3"]) for o, j in h]; b = [sim(o, land_time(o, j, ("S1", 0.5)), EXITS["t3"]) for o, j in h]
        print(f"  Y>={Y:<4} {setn:5} n={len(h):3} S+100 {st.mean(a):+6.1%} (med {st.median(a):+6.1%}) | S1mid {st.mean(b):+6.1%} (med {st.median(b):+6.1%})")

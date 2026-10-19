#!/usr/bin/env python3
# READ-ONLY cross-check of racedeep sim vs the race agent's hc_search.sim on the same night launches.
import sys, statistics as st
sys.path.insert(0, "/root/racedeep"); sys.path.insert(0, "/root/race")
from hc_search import sim as hsim, EXITS as HX, hostbad
from fwdrows import build
from rdlib import load, sim, land_time, EXITS
F = [o for o in build("/root/racedeep/snap/paper_night.log", "/root/racedeep/snap/night_onchain.jsonl", "/root/racedeep/snap/paths_night.jsonl", verbose=False) if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
U = {o["mint"]: o for o in load() if o["set"] == "night"}
RACE = lambda o: o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3
for nm, fn in (("race", RACE), ("gateB", lambda o: o["dev_sol"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12), ("all", lambda o: True)):
    g = [o for o in F if fn(o) and o["mint"] in U]
    for d in (5, 25, 100):
        a = [hsim(o, HX["time 1s"], d_land=d) for o in g]
        b = [sim(U[o["mint"]], land_time(U[o["mint"]], -1, ("S", d)), EXITS["t1"]) for o in g]
        # my sim but with THEIR path (timing) to isolate the timing effect
        print(f"{nm:6} n={len(g)} d{d}: race-agent sim {st.mean(a):+.1%} | racedeep sim {st.mean(b):+.1%}")
    a = [hsim(o, HX["time 1s"], land_s1=True) for o in g]
    print(f"{nm:6} S+1 (race agent: front of S+1): {st.mean(a):+.1%}")
# timing diagnostics
o = U[g[0]["mint"]]
import statistics
print("median tS (ms after create to end of S):", statistics.median(u["tS"] for u in U.values()))

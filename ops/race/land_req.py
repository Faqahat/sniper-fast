#!/usr/bin/env python3
# READ-ONLY. "The exact gap": realistic return (hc_search.sim: 2 SOL, x1.03, fees, 0.009 SOL prio) of each gate as a function of
# WHERE in slot S we land (behind the first d non-vote txs after the create), historical TEST + forward run 1 pooled, exits 1 s / 3 s.
import sys, json, statistics as st
sys.path.insert(0, "/root/race")
from hc_search import sim, EXITS, stats, hostbad
from fwdrows import build
R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
U = [r for r in R if not r["quote"] and not r["mayhem"] and not hostbad(r.get("uri_host")) and 0.5 <= r["dev_sol"] <= 8 and r["has_path"] and not r.get("bad_ev")]
U.sort(key=lambda r: r["slot"])
cut = U[int(len(U) * 0.6)]["slot"]
HT = [r for r in U if r["slot"] >= cut and r["in_rand"]]
HH = [r for r in U if r["slot"] >= cut and r["his"]]
F = [o for o in build(*sys.argv[1:4], verbose=False) if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
G = {"FIX base (no gate)": lambda r: True,
     "GATE B (dev>=3 & bundle>=2tx & name<=12)": lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2 and r["n_len"] <= 12,
     "dev>=2": lambda r: r["dev_sol"] >= 2,
     "HINDSIGHT race (>=3 outsiders & >=3 SOL in 2 s)": lambda r: r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3}
DS = (1, 5, 10, 25, 50, 100, 150)
for xn in ("time 1s", "time 3s"):
    print(f"\n== exit {xn}: mean realistic return / median, landing behind the first d txs of S")
    print(f"{'set':52} {'n':>4} | " + " | ".join(f"d={d:<3}        " for d in DS))
    for nm, fn in G.items():
        g = [r for r in HT if fn(r)] + [o for o in F if fn(o)]
        cells = []
        for d in DS:
            v = [sim(r, EXITS[xn], d_land=d) for r in g]
            cells.append(f"{st.mean(v):+5.1%}/{st.median(v):+5.1%}")
        print(f"{nm:52} {len(g):4} | " + " | ".join(cells))
    for nm, g in (("4yFAz picks (hist test)", HH), ("4yFAz picks (fwd run1)", [o for o in F if o["his"]])):
        cells = []
        for d in DS:
            v = [sim(r, EXITS[xn], d_land=d) for r in g]
            cells.append(f"{st.mean(v):+5.1%}/{st.median(v):+5.1%}")
        print(f"{nm:52} {len(g):4} | " + " | ".join(cells))

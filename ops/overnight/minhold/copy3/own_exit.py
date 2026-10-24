#!/usr/bin/env python3
# OUR OWN EXIT on copied first buys (read-only, uses out/copy_rows.pkl.gz from a3_copy.py). We copy ONLY their first buy; we never look
# at their sells. 300+ own exit rules (TP/SL/time up to 10 min, trailing, idle, follower-flow, outside-sell). Picks a rule on one run and
# tests it on the others, per wallet set, latency T, follower variant, and price guard. Also: how many rules are positive on all 3 runs.
import gzip, pickle, collections, statistics, json
D = pickle.load(gzip.open("out/copy_rows.pkl.gz", "rb")); N = D["names"]; RW = D["rows"]
HRS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}; FAIL = 0.0005
OWN = [i for i, n in enumerate(N) if not n.startswith("mir")]
G = collections.defaultdict(list)
for r in RW: G[(r["w"], r["run"], r["T"], r["B"], r["var"])].append(r)
SETS = {"ALL": ["Fsb6Ns75", "pXGQ6J2z", "4vw54BmA"], "Fsb6+pXGQ": ["Fsb6Ns75", "pXGQ6J2z"], "Fsb6": ["Fsb6Ns75"], "pXGQ": ["pXGQ6J2z"], "4vw54": ["4vw54BmA"]}
def tot(ws, run, T, var, ri, guard, exg, B=1.0):
    s = 0.0; n = 0
    for w in ws:
        for r in G[(w, run, T, B, var)]:
            if guard is not None and r["entry_vs_them"] > 1 + guard: s -= FAIL; continue
            if exg and ri in r["grad_rules"]: continue
            s += r["pnl"][ri]; n += 1
    return s, n
out = []
print("OWN EXITS ONLY (no mirroring), B = 1 SOL. 'pick on X' = best own rule on run X, then its result on the other runs (SOL).")
for T in (35, 75):
    for var in ("slip", "drop2"):
        for guard in (None, 0.05, 0.10):
            for sname, ws in SETS.items():
                for exg in (False, True):
                    R = {run: [tot(ws, run, T, var, ri, guard, exg)[0] for ri in OWN] for run in ("R1", "R2", "R3")}
                    allpos = sum(1 for k in range(len(OWN)) if all(R[run][k] > 0 for run in R))
                    best_min = max(range(len(OWN)), key=lambda k: min(R[run][k] for run in R))
                    picks = {}
                    for tr in ("R2", "R3"):
                        k = max(range(len(OWN)), key=lambda k: R[tr][k])
                        picks[tr] = (N[OWN[k]], {run: R[run][k] for run in R})
                    k23 = max(range(len(OWN)), key=lambda k: R["R2"][k] + R["R3"][k])
                    row = dict(T=T, var=var, guard=guard, set=sname, exg=exg, allpos=allpos, nrules=len(OWN),
                               best_min=(N[OWN[best_min]], {run: R[run][best_min] for run in R}), picks=picks, pick23=(N[OWN[k23]], R["R1"][k23]),
                               median_rule={run: statistics.median(R[run]) for run in R})
                    out.append(row)
json.dump(out, open("out/own_exit.json", "w"))
f = lambda d: " / ".join(f"{d[r]:+5.1f}" for r in ("R2", "R3", "R1"))
for row in out:
    if row["exg"] or row["var"] != "slip": continue
    g = "none" if row["guard"] is None else f"{int(row['guard']*100)}%"
    pn2, d2 = row["picks"]["R2"]; pn3, d3 = row["picks"]["R3"]; bm, dm = row["best_min"]
    print(f"T={row['T']:3d} guard {g:4s} {row['set']:9s} | rules positive on all 3 runs: {row['allpos']:3d}/{row['nrules']} | median rule R2/R3/R1 {f(row['median_rule'])} | "
          f"pick on R2 → {pn2:18s} R2/R3/R1 {f(d2)} | pick on R3 → {pn3:18s} {f(d3)} | pick on R2+R3 → R1 {row['pick23'][1]:+5.1f} ({row['pick23'][0]}) | most robust {bm} {f(dm)}")

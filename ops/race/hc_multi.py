#!/usr/bin/env python3
# READ-ONLY. Multi-period robust gate+exit search at REALISTIC prices (hc_search.sim: 2 SOL, land S @<=100, x1.03, 0.009 SOL
# buy prio). Three periods: P1 historical train (first 60%), P2 historical test (last 40%), P3 forward run 1 (a census of every
# base launch, 2 h). A rule's score = the WORST period mean (each period needs >= MIN_N trades) with its best exit; median and
# ex-top3 shown. The top rules are written to /root/race/PREREG.json to be judged on the overnight run (P4) only.
# usage: hc_multi.py paper_fwd.log fwd_onchain.jsonl paths_fwd.jsonl [min_n]
import json, sys, itertools, statistics as st, time
sys.path.insert(0, "/root/race")
from hc_search import sim, EXITS, stats, fmt, hostbad, C
from fwdrows import build

MIN_N = int(sys.argv[4]) if len(sys.argv) > 4 else 15
XS = ["time 0.4s", "time 0.6s", "time 1s", "time 1.5s", "time 2s", "time 3s", "time 5s", "tp1.2 T3s slNone", "tp1.3 T10s slNone", "half@1.2 half@1.5 T3s",
      "half@1.1 half@1.5 T3s", "whale>=2SOL sell 1 T3s", "whale>=1SOL sell 0.5 T3s", "trail0.9 T10s +half@1.2"]
R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
H = [r for r in R if r["in_rand"] and not r["quote"] and not r["mayhem"] and not hostbad(r.get("uri_host")) and 0.5 <= r["dev_sol"] <= 8 and r["has_path"] and not r.get("bad_ev")]
H.sort(key=lambda r: r["slot"])
cut = H[int(len(H) * 0.6)]["slot"]
F = [o for o in build(*sys.argv[1:4]) if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
P = {"P1 hist-train": [r for r in H if r["slot"] < cut], "P2 hist-test": [r for r in H if r["slot"] >= cut], "P3 fwd run1": F}
print(f"periods: " + ", ".join(f"{k} n={len(v)}" for k, v in P.items()) + f" | min n per period {MIN_N}")
t0 = time.time()
PN = {pk: {xn: [sim(r, EXITS[xn]) for r in rows] for xn in XS} for pk, rows in P.items()}
M = {pk: {cn: [fn(r) for r in rows] for cn, fn in C.items()} for pk, rows in P.items()}
print(f"precomputed in {time.time() - t0:.0f}s; {len(C)} conditions x {len(XS)} exits")
print("\n-- baseline (no gate):")
for xn in XS[:5]:
    print("   " + xn.ljust(26) + " | ".join(f"{pk}: {st.mean(PN[pk][xn]):+.1%}" for pk in P))
res = []
names = list(C)
for k in (1, 2, 3):
    for combo in itertools.combinations(names, k):
        sel = {}
        ok = True
        for pk in P:
            m = M[pk]
            idx = [i for i in range(len(P[pk])) if all(m[c][i] for c in combo)]
            if len(idx) < MIN_N:
                ok = False
                break
            sel[pk] = idx
        if not ok:
            continue
        best = None
        for xn in XS:
            means = [st.mean([PN[pk][xn][i] for i in sel[pk]]) for pk in P]
            meds = [st.median([PN[pk][xn][i] for i in sel[pk]]) for pk in P]
            sc = min(means)
            if best is None or sc > best[0]:
                best = (sc, xn, means, meds)
        res.append((best[0], combo, best[1], best[2], best[3], {pk: len(v) for pk, v in sel.items()}))
res.sort(key=lambda z: -z[0])
print(f"\n-- {len(res)} rules with >= {MIN_N} trades in every period; top 25 by WORST-period mean (exit chosen per rule by the same criterion)")
print(f"{'rule':66} {'exit':24} | " + " | ".join(f"{pk:>22}" for pk in P))
for sc, combo, xn, means, meds, ns in res[:25]:
    print(f"{' & '.join(combo)[:66]:66} {xn:24} | " + " | ".join(f"n{ns[pk]:3} {mu:+6.1%} med {md:+6.1%}" for pk, mu, md in zip(P, means, meds)))
# a median-aware view: rules whose worst-period MEDIAN is best
res2 = sorted(res, key=lambda z: -min(z[4]))
print(f"\n-- top 10 by WORST-period MEDIAN (with that rule's exit)")
for sc, combo, xn, means, meds, ns in res2[:10]:
    print(f"{' & '.join(combo)[:66]:66} {xn:24} | " + " | ".join(f"n{ns[pk]:3} {mu:+6.1%} med {md:+6.1%}" for pk, mu, md in zip(P, means, meds)))
prereg = [{"rule": list(combo), "exit": xn, "score": sc, "means": means, "meds": meds, "ns": ns} for sc, combo, xn, means, meds, ns in res[:5]]
json.dump({"written_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "prereg": prereg}, open("/root/race/PREREG_v2.json", "w"), indent=1)
print("\nPREREG_v2.json written (top 5 by worst-period mean) — to be judged ONLY on the overnight run.")

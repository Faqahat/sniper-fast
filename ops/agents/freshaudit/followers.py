#!/usr/bin/env python3
# who buys right after >=1 SOL dumps (all dumps, r3), how fast (block index gap), through which paths, how often they fail
import sys, json, gzip, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from load import load
A = "/home/moiz/sniper/ops/agents/freshaudit"
run = sys.argv[1] if len(sys.argv) > 1 else "r3"
W = collections.defaultdict(lambda: dict(n=0, ok=0, fail=0, ss=0, didx=[], sol=0.0, rel=collections.Counter(), tip=[], cup=[], errs=collections.Counter(), first=0, dumps=set()))
nd = 0; nd_any = 0; first_ss = collections.Counter(); first_didx = []
for l in gzip.open(f"{A}/out/comp_{run}.jsonl.gz", "rt"):
    d = json.loads(l)
    if d["sol"] < 1.0 or d["vsol"] > 110e9 or d["vsol"] < 25e9: continue
    nd += 1
    seen_first = False
    for f in d["fol"]:
        ds, i, sg, err, isbuy, sol, pr, rel, tip, cup, cul, fee, progs, user, sig = f
        if not isbuy or ds > 1: continue
        w = W[sg]; w["n"] += 1; w["dumps"].add(d["sig"])
        if err: w["fail"] += 1; w["errs"][str(err).split(":")[-1]] += 1
        else:
            w["ok"] += 1; w["sol"] += sol or 0
            if not seen_first:
                seen_first = True; w["first"] += 1
                if ds == 0: first_didx.append(i - d["i"])
                first_ss[ds] += 1
        if ds == 0: w["ss"] += 1; w["didx"].append(i - d["i"])
        w["rel"][rel] += 1
        if tip: w["tip"].append(tip)
        if cup: w["cup"].append(cup)
    if seen_first: nd_any += 1
print(f"dumps >=1 SOL (curve 25-110 SOL): {nd}; with an ok follower buy in slot+0/+1: {nd_any} ({nd_any/nd:.0%}); first ok follower same-slot {first_ss[0]} next-slot {first_ss[1]}")
print(f"first follower same-slot dIdx: median {st.median(first_didx)}, p10 {sorted(first_didx)[len(first_didx)//10]}, p25 {sorted(first_didx)[len(first_didx)//4]}")
rows = []
for sg, w in W.items():
    if w["n"] < 30: continue
    rows.append((sg, w))
rows.sort(key=lambda x: -x[1]["first"])
print(f"\n{'wallet':<10} {'attempts':>8} {'ok':>6} {'fail%':>6} {'first':>6} {'ss%':>5} {'dIdx med':>8} {'p10':>5} {'SOL':>8} {'tip med':>8} {'cup med':>9}  relays / errs")
for sg, w in rows[:45]:
    dm = st.median(w["didx"]) if w["didx"] else float("nan"); p10 = sorted(w["didx"])[len(w["didx"]) // 10] if w["didx"] else float("nan")
    print(f"{sg[:10]:<10} {w['n']:>8} {w['ok']:>6} {w['fail']/w['n']:>6.0%} {w['first']:>6} {w['ss']/w['n']:>5.0%} {dm:>8.0f} {p10:>5.0f} {w['sol']:>8.1f} {st.median(w['tip'])/1e6 if w['tip'] else 0:>8.2f} {st.median(w['cup'])/1e6 if w['cup'] else 0:>9.2f}  {dict(w['rel'].most_common(3))} {dict(w['errs'].most_common(2))}")
json.dump({sg: dict(n=w["n"], ok=w["ok"], fail=w["fail"], first=w["first"], ss=w["ss"], didx_med=(st.median(w["didx"]) if w["didx"] else None), sol=w["sol"], rel=dict(w["rel"]), errs=dict(w["errs"])) for sg, w in rows},
          open(f"{A}/out/followers_{run}.json", "w"))

#!/usr/bin/env python3
# For FIRST baits only (k=1): does the baiter's earlier pump.fun activity that day change follower response?
# Pass 1 = bait events (b8 job); pass 2 = every trade slot of those baiter wallets in the run.
import gzip, json, collections, statistics as st, bisect, sys
from multiprocessing import Pool
import b1_scan as B, b8_repeat as R8
if len(sys.argv) > 1 and sys.argv[1] == "R4": B.RUNS = {"R4": ["phaseA_r4"]}
W = set()
def job2(a):
    run, b = a; out = collections.defaultdict(list)
    for m, tr in B.read(run, b).items():
        for t in tr:
            if t[7] in W: out[t[7]].append((t[0], t[8], t[9]))
    return run, out
def initw(ws):
    global W; W = ws
if __name__ == "__main__":
    E = []
    with Pool(12) as p:
        for e in p.imap_unordered(R8.job, [(r, b) for r in B.RUNS for b in range(256)]): E += e
    E.sort(key=lambda x: (x[0], x[2])); seen = set(); first = []
    for e in E:
        if (e[0], e[1]) not in seen: seen.add((e[0], e[1])); first.append(e)
    ws = {e[1] for e in first}; H = collections.defaultdict(list)
    with Pool(12, initializer=initw, initargs=(ws,)) as p:
        for run, out in p.imap_unordered(job2, [(r, b) for r in B.RUNS for b in range(256)]):
            for w, v in out.items(): H[(run, w)] += v
    for k in H: H[k].sort()
    rows = []
    for e in first:
        h = H[(e[0], e[1])]; prior = [x for x in h if x[0] < e[2]]
        after = [x for x in h if x[0] > e[2] + 60]
        rows.append((e, len(prior), (e[2] - prior[0][0]) if prior else -1, len(after)))
    def show(name, f, bins):
        print(f"\n-- first baits by {name}")
        for lo, hi in bins:
            rs = [r for r in rows if lo <= f(r) < hi]
            if len(rs) < 50: continue
            print(f"  {lo:>6}-{hi:<7} n={len(rs):5d}  follower<=1 slot {100*sum(r[0][4]>0 for r in rs)/len(rs):4.0f}%  follower SOL {st.mean(r[0][5] for r in rs):.2f}  px+20 {st.mean(r[0][6] for r in rs):.4f}")
    show("pump trades earlier that day", lambda r: r[1], [(0, 1), (1, 3), (3, 11), (11, 51), (51, 10**7)])
    show("slots since first trade that day (0 = none)", lambda r: r[2] if r[2] >= 0 else -1, [(-1, 0), (0, 3000), (3000, 30000), (30000, 10**9)])
    show("pump trades LATER that day (does it become a bot?)", lambda r: r[3], [(0, 3), (3, 11), (11, 51), (51, 10**7)])

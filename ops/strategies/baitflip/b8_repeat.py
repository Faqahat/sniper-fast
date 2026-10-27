#!/usr/bin/env python3
# Quiet-token bait (rule 336 trigger: buy 0.75-3 SOL, quiet >= 40 slots, age >= 150, curve <= 40): do followers still
# answer a wallet that baits OFTEN? Follower response by the baiter's running bait count that day (k-th bait) and by
# the baiter's total baits. Also simple P&L proxy: price 20 / 60 slots later vs fill (no costs) for each group.
import gzip, json, collections, statistics as st, sys
from multiprocessing import Pool
import b1_scan as B
RUNS = dict(B.RUNS)
if len(sys.argv) > 1 and sys.argv[1] == "R4": RUNS = {"R4": ["phaseA_r4"]}
B.RUNS = RUNS
def job(a):
    run, b = a; ev = []
    for m, tr in B.read(run, b).items():
        if len(tr) < 5 or any(t[11] < 25e9 or t[11] > 200e9 or not t[12] for t in tr[:50]): continue
        s0 = tr[0][0]; n = len(tr)
        for k in range(1, n):
            t = tr[k]
            if t[11] >= B.GRADV: break
            if not t[8] or not (0.75e9 <= t[9] <= 3e9): continue
            if t[0] - tr[k - 1][0] < 40 or t[0] - s0 < 150: continue
            pv, pt = B.pre(t)
            if pv > 40e9: continue
            fill = B.px(t[11], t[12]); nb = 0; bs = 0.0; p20 = p60 = fill; seenf = False
            for z in tr[k + 1:]:
                if z[0] > t[0] + 60 or z[11] >= B.GRADV: break
                if z[7] != t[7] and z[8] and z[0] <= t[0] + 1: nb += 1; bs += z[9]
                if z[7] == t[7]: continue
                p = B.px(z[11], z[12])
                if z[0] <= t[0] + 20: p20 = p
                p60 = p
            ev.append((run, t[7], t[0], round(t[9] / 1e9, 3), nb, round(bs / 1e9, 3), round(p20 / fill, 4), round(p60 / fill, 4)))
    return ev
if __name__ == "__main__":
    E = []
    with Pool(12) as p:
        for e in p.imap_unordered(job, [(r, b) for r in RUNS for b in range(256)]): E += e
    E.sort(key=lambda x: (x[0], x[2]))
    tot = collections.Counter((e[0], e[1]) for e in E); kth = collections.Counter(); rows = []
    for e in E:
        kth[(e[0], e[1])] += 1; rows.append((e, kth[(e[0], e[1])], tot[(e[0], e[1])]))
    def show(name, f, bins):
        print(f"\n-- by {name}")
        for lo, hi in bins:
            rs = [e for e, k, T in rows if lo <= f(e, k, T) < hi]
            if len(rs) < 50: continue
            print(f"  {lo:>4}-{hi:<5} baits={len(rs):6d} wallets={len({e[1] for e in rs}):5d}  follower within 1 slot {100*sum(e[4]>0 for e in rs)/len(rs):4.0f}%"
                  f"  follower SOL {st.mean(e[5] for e in rs):.2f}  px+20 {st.mean(e[6] for e in rs):.4f}  px+60 {st.mean(e[7] for e in rs):.4f}")
    print("total baits", len(rows), "by run", collections.Counter(e[0] for e in E))
    show("k-th bait of this wallet that day", lambda e, k, T: k, [(1, 2), (2, 6), (6, 21), (21, 101), (101, 10**6)])
    show("wallet's total baits that day", lambda e, k, T: T, [(1, 2), (2, 6), (6, 21), (21, 101), (101, 10**6)])
    big = [w for w, c in tot.items() if c >= 50]
    print("\nwallets with >=50 baits/day:", len(big))
    for w in sorted(big, key=lambda w: -tot[w])[:12]:
        rs = [e for e, k, T in rows if (e[0], e[1]) == w]
        h = len(rs) // 2
        f = lambda xs: 100 * sum(e[4] > 0 for e in xs) / len(xs)
        print(f"  {w[0]} {w[1][:8]} baits={len(rs):5d} size~{st.median(e[3] for e in rs):.2f}  follow 1st half {f(rs[:h]):3.0f}% 2nd half {f(rs[h:]):3.0f}%  px+20 {st.mean(e[6] for e in rs):.4f}")

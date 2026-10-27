#!/usr/bin/env python3
# Do dip bots' buys FAIL (price guard) when the dump was already restored? Failed pump txs = "X" rows with err.
# For each sell >= 0.5 SOL: count known-dip-bot successful buys and failed txs in the same slot after it, split by
# whether the next trade restored the price (rest_full) or not (dump).
import gzip, json, glob, collections, sys
from multiprocessing import Pool
import b1_scan as B
PFX = ("haqqiUUX", "HkQ7hMjy", "DYXDDrZC", "E6JasdE8", "7PedQZm", "CZ77onJz", "6VzXcLk9", "ETwEAQPL", "sssssDdM", "ssssswdk", "9pQQc1xy")
def job(a):
    run, b = a
    T = collections.defaultdict(list); X = collections.defaultdict(list)
    for d in B.RUNS[run]:
        d = d if d.startswith("/") else f"{B.D}/{d}"
        for f in glob.glob(f"{d}/b{b:03d}/*.jsonl.gz"):
            try:
                for line in gzip.open(f, "rt"):
                    r = json.loads(line)
                    if r[0] == "X" and r[12]: X[r[1]].append((r[2], r[3], r[6]))
            except Exception: pass
    tr_all = B.read(run, b)
    c = collections.Counter()
    for m, tr in tr_all.items():
        xs = collections.defaultdict(list)
        for s, i, p in X.get(m, []): xs[s].append((i, p))
        for k, t in enumerate(tr):
            if t[8] or t[9] < 0.5e9 or k + 1 >= len(tr): continue
            pv, pt = B.pre(t); p0 = B.px(pv, pt); nx = tr[k + 1]
            kind = "rest" if (nx[0] == t[0] and nx[8] and nx[7] != t[7] and 0.985 <= B.px(nx[11], nx[12]) / p0 <= 1.02) else \
                   ("part" if (nx[0] == t[0] and nx[8]) else "dump")
            c[kind + "_n"] += 1
            ok = sum(1 for z in tr[k + 1:k + 60] if z[0] == t[0] and z[8] and z[7].startswith(PFX))
            fl = sum(1 for i, p in xs.get(t[0], []) if i > t[1] and p.startswith(PFX))
            fl_any = sum(1 for i, p in xs.get(t[0], []) if i > t[1])
            c[kind + "_ok"] += ok; c[kind + "_fail"] += fl; c[kind + "_failany"] += fl_any
    return c
if __name__ == "__main__":
    tot = collections.Counter()
    with Pool(12) as p:
        for c in p.imap_unordered(job, [(r, b) for r in ["R2", "R3"] for b in range(0, 256, 4)]): tot.update(c)
    for k in ["rest", "part", "dump"]:
        n = tot[k + "_n"]
        print(f"{k:5} sells={n:7d}  dip-bot buys ok/sell={tot[k+'_ok']/n:.3f}  dip-bot FAILED/sell={tot[k+'_fail']/n:.3f}  "
              f"fail share={tot[k+'_fail']/max(1,tot[k+'_ok']+tot[k+'_fail']):.2f}  any failed pump tx after/sell={tot[k+'_failany']/n:.3f}")

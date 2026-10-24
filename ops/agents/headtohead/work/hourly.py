#!/usr/bin/env python3
# read-only: competition intensity by hour (PKT) over both recordings, from decoded trade tapes (sampled buckets).
# dump = sell >= 1 SOL on a token <= 10 min old; race metrics with a 0.35 SOL +5% reference buy.
import os, sys, json, gzip, glob, zlib, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
SETS = [("run_20261022_1543", "phaseA_selfwd"), ("run_20261023_1426", "phaseA_r3day")]
SOL_IN = 345679011
def tok_out(V, T, x): return T - (V * T + (V + x) - 1) // (V + x)
CREATE = {}
for run, _ in SETS:
    for l in open(os.path.join(D, run, "launches.jsonl")):
        try: c = json.loads(l); CREATE.setdefault(c["mint"], c["bt"])
        except Exception: pass
def work(b):
    rows = collections.defaultdict(list)
    for run, pa in SETS:
        for f in glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[12]: continue
                    rows[r[1]].append((r[2], r[3], r[13], r[4], r[6], r[15], r[16], r[18], r[19], r[8] or 0))
            except (EOFError, OSError, zlib.error): pass
    out = []
    for m, tr in rows.items():
        cbt = CREATE.get(m)
        if cbt is None: continue
        tr = sorted(set(tr))
        for k, (s, i, j, bt, payer, buy, sol, V, T, cup) in enumerate(tr):
            if buy or sol < 1e9 or bt - cbt > 600: continue
            base = tok_out(V, T, SOL_IN); lim = base * 100 // 105
            first = None; nbuy_before_cross = 0; crossed = None; vv, tt = V, T; buyers = set()
            for (s2, i2, j2, bt2, p2, b2, sol2, V2, T2, cup2) in tr[k + 1:]:
                if s2 > s + 2: break
                if b2 and p2 != payer and first is None: first = (s2 - s, i2 - i if s2 == s else None)
                vv, tt = V2, T2
                if b2 and crossed is None: buyers.add(p2)
                if crossed is None and tok_out(vv, tt, SOL_IN) < lim: crossed = (s2 - s)
            hour = (bt + 5 * 3600) % 86400 // 3600
            out.append((hour, first, crossed, len(buyers)))
    return out
if __name__ == "__main__":
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    agg = collections.defaultdict(lambda: [0, 0, 0, [], 0])
    with Pool(4) as pool:
        for res in pool.imap_unordered(work, range(0, 256, step)):
            for hour, first, crossed, nb in res:
                a = agg[hour]; a[0] += 1
                if crossed == 0: a[1] += 1
                if first and first[0] == 0: a[2] += 1; 
                if first and first[0] == 0 and first[1] is not None: a[3].append(first[1])
                a[4] += nb
    print("hour(PKT) dumps  crossed+5%%_in_dump_block  first_buyer_in_dump_block  median_first_buyer_idx_gap  mean_buyers_before_cross")
    for h in sorted(agg):
        a = agg[h]; v = sorted(a[3])
        print("  %02d  %6d   %5.1f%%   %5.1f%%   %4s   %.2f" % (h, a[0], 100 * a[1] / a[0], 100 * a[2] / a[0], v[len(v) // 2] if v else '-', a[4] / a[0]))

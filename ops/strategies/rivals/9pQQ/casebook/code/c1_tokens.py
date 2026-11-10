#!/usr/bin/env python3
"""CASEBOOK step 1: per-token summary of 9pQQ's trips (for deliberate case selection).
out: casebook/tokens_<run>.tsv"""
import sys, json, collections, datetime
OUT = "/home/it/sniper-data/rivals/9pQQ/casebook"; COL = "/data/tapes/collect"
for run in sys.argv[1:]:
    L = {}
    for l in open(f"{COL}/{run}/launches.jsonl"):
        d = json.loads(l); L[d["mint"]] = (d["slot"], d["bt"])
    T = collections.defaultdict(list)
    for l in open(f"{OUT}/trips_{run}.jsonl"):
        t = json.loads(l); T[t["mint"]].append(t)
    with open(f"{OUT}/tokens_{run}.tsv", "w") as fo:
        fo.write("mint\tn\tnet_mSOL\tbest\tworst\tfirst_age\tfirst_pkt\tspan_min\tlaunched_in_run\twins\n")
        for m, ts in T.items():
            ts.sort(key=lambda t: t["bs"])
            ls = L.get(m)
            age = ts[0]["bs"] - ls[0] if ls else -1
            pk = (datetime.datetime.utcfromtimestamp(ts[0]["bbt"]) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M")
            span = (ts[-1]["sbt"] - ts[0]["bbt"]) / 60
            nets = [t["net"] / 1e6 for t in ts]
            fo.write(f"{m}\t{len(ts)}\t{sum(nets):.1f}\t{max(nets):.1f}\t{min(nets):.1f}\t{age}\t{pk}\t{span:.1f}\t{int(bool(ls))}\t{sum(n > 0 for n in nets)}\n")
    print(run, len(T), "tokens;", sum(1 for m in T if m in L), "launched in run")

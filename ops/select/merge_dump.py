#!/usr/bin/env python3
# Join the anti-dump features (f_dump.py) onto the joined table and add the labels: y_dump5 (price <= 0.85x within 5 s
# of the post-bundle price), y_good (not a fast dump and >= 1.1x at 30 s or 10-min peak >= 1.5x). Outcome fields keep a
# y_ prefix so no model can take them as features. usage: merge_dump.py <table_all.jsonl.gz> <dump_feats.jsonl.gz> <out.jsonl.gz>
import sys, json, gzip
T, F_, OUT = sys.argv[1:4]
F = {}
for l in gzip.open(F_, "rt"):
    r = json.loads(l); m = r.pop("mint")
    for k in ("fast", "ins_first_s", "ins_out_s"): r["y_" + k] = r.pop(k)
    F[m] = r
n = 0
with gzip.open(OUT, "wt") as fo:
    for l in gzip.open(T, "rt"):
        r = json.loads(l); r.update(F.get(r["mint"], {}))
        p2, p5, p30, pk = r.get("px_2s"), r.get("px_5s"), r.get("px_30s"), r.get("peak_10m")
        if p5 is not None:
            r["y_dump5"] = int(min(p2 or 1, p5) <= 0.85)
            r["y_good"] = int(not r["y_dump5"] and ((p30 or 0) >= 1.1 or (pk or 0) >= 1.5))
        fo.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1
print("rows", n)

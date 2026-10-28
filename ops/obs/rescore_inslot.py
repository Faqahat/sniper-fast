#!/usr/bin/env python3
"""rescore_inslot.py OBS_FILE [--d 15] — re-score INSLOT from an obs file's inslot records (dip24 summaries counted every >= 1 SOL
sell of one dump cluster separately and were snapshots at their 10-min mark). One record per cluster (the first sell of a token while
no earlier one <= 3 slots before is open), net mSOL per fill = (value - 1) x size - 3.3 mSOL (0.5 prio + 1.0 tip + 1.8 sell), a fail -0.15.
Groups: all / profile / rival_took / profile_and_took; rows: D x hold (3/6/9/61 slots) x size."""
import sys, json, collections
f = sys.argv[1]; D = sys.argv[sys.argv.index("--d") + 1] if "--d" in sys.argv else None
recs = [json.loads(l) for l in open(f) if l.endswith("\n") and '"ev":"inslot"' in l]
recs.sort(key=lambda r: (r["mint"], r["slot"], r["idx"]))
keep, last = [], {}
for r in recs:
    p = last.get(r["mint"])
    if p is None or r["slot"] > p + 3: keep.append(r)
    last[r["mint"]] = r["slot"]
agg = collections.defaultdict(lambda: collections.defaultdict(lambda: {"fills": 0, "fails": 0, "net": [[0.0] * 4, [0.0] * 4]}))
for r in keep:
    gs = ["all"] + (["profile"] if r["profile"] else []) + (["rival_took"] if r.get("took") else []) + (["profile_and_took"] if r["profile"] and r.get("took") else [])
    for d, l in r["legs"].items():
        if D and d != D: continue
        for g in gs:
            a = agg[g][d]
            if l["res"] == "fill":
                a["fills"] += 1
                for si, sz in enumerate(("0.50", "0.75")):
                    for h, v in enumerate(l["v"][sz]):
                        if v is not None: a["net"][si][h] += (v - 1) * float(sz) * 1000 - 3.3
            elif l["res"].startswith("fail"):
                a["fails"] += 1
                for si in range(2):
                    for h in range(4): a["net"][si][h] -= 0.15
print(f"{len(recs)} inslot records -> {len(keep)} dump clusters")
for g, ds in agg.items():
    for d, a in sorted(ds.items()):
        n = a["fills"]
        print(f"{g:17} D={d:9} fills {n:5} fails {a['fails']:4} | net SOL 0.50 @3/6/9/61 {[round(x/1000,3) for x in a['net'][0]]} | per fill mSOL {[round(x/max(n,1),1) for x in a['net'][0]]}")

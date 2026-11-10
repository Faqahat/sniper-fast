#!/usr/bin/env python3
"""VERIFY step 12 [PAPER]: STATE's nbuyers50 skip on the 9 shadow-only runs (engine shadow rows a/c exits; arms with trigger age >= 2).
Own extraction + own tape (same decoded sources as v5)."""
import json, pickle, collections, sys, time
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/verify")
D = "/home/it/sniper-data"; OUT = f"{D}/prevent/verify"
RUNS = {f"A{r}": f"{D}/runs/ams/runs/dip_ams_r{r}.jsonl" for r in (14, 15, 21, 22, 23)}
RUNS.update({f"F{r}": f"{D}/runs/fra/runs/dip_r{r}.jsonl" for r in (15, 16, 20, 25)})
SRC = [("chain", f"{D}/presend_quiet3", 0, 462709231), ("chain", f"{D}/presend_young/ext", 462709231, 462710488),
       ("tab", f"{D}/paper_audit/tab", 462710488, 463010350)]
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
arms = []; exits = {}
for run, p in RUNS.items():
    sess = 0
    with open(p, "rb") as fh:
        for raw in fh:
            if b'"ev":"run_start"' in raw: sess += 1; continue
            if b'"ev":"presend_arm"' in raw:
                d = json.loads(raw); arms.append(dict(run=run, s=sess, w=d["w"], mint=d["mint"], slot=d["slot"], idx=d["idx"], who=d.get("wallet"), age=d.get("age_slots"), t=d.get("t")))
            elif b'"ev":"presend_exit"' in raw:
                d = json.loads(raw)
                if d.get("pnl") is not None: exits[(run, sess, d["w"], d["row"])] = d["pnl"]
need = {a["mint"] for a in arms}
print("shadow arms", len(arms), "mints", len(need), "exits", len(exits), flush=True)
rows = collections.defaultdict(list)
for kind, path, lo, hi in SRC:
    if kind == "chain":
        z = np.load(f"{path}/chain.npz"); I = json.load(open(f"{path}/ids.json")); ml, ul = I["mint"], I["user"]
        want = np.array([m in need for m in ml], bool); cm = z["mint"]; s = z["s"]
        ix = np.nonzero(want[cm] & (s >= lo) & (s < hi))[0]
        for k, m, sl, i, b, u in zip(ix.tolist(), cm[ix].tolist(), s[ix].tolist(), z["i"][ix].tolist(), z["buy"][ix].tolist(), z["user"][ix].tolist()):
            rows[ml[m]].append((sl, i, b, ul[u]))
    else:
        A = np.load(f"{path}/trades.npy"); ids = json.load(open(f"{path}/ids.json"))
        want = np.array([m in need for m in ids], bool); A = A[want[A["mint"]] & (A["slot"] >= lo) & (A["slot"] < hi)]
        for m, sl, i, b, u in zip(A["mint"].tolist(), A["slot"].tolist(), A["idx"].tolist(), A["buy"].tolist(), A["user"].tolist()):
            rows[ids[m]].append((sl, i, b, ids[u]))
for m in rows: rows[m].sort()
res = collections.defaultdict(lambda: collections.Counter())
for a in arms:
    if (a["age"] if a["age"] is not None else 99) < 2: continue
    R = rows.get(a["mint"])
    if not R: res[a["run"]]["notape"] += 1; continue
    buyers = {u for (sl, i, b, u) in R if b and u not in OURS and a["slot"] - 49 <= sl and (sl, i) <= (a["slot"], a["idx"])}
    skip = len(buyers) <= 1
    r = res[a["run"]]; r["arms"] += 1; r["skip"] += skip
    for row in ("a", "c"):
        v = exits.get((a["run"], a["s"], a["w"], row))
        if v is None: continue
        r[f"fills_{row}"] += 1
        if skip: r[f"save_{row}"] += -v; r[f"skipfills_{row}"] += 1
tot = collections.Counter()
for run in RUNS:
    r = res[run]; tot.update(r)
    print(f"{run}: arms(age>=2) {r['arms']} skipped {r['skip']} | row a fills {r['fills_a']} skipped {r['skipfills_a']} save {r['save_a']:+.3f} | row c fills {r['fills_c']} skipped {r['skipfills_c']} save {r['save_c']:+.3f} | no tape {r['notape']}")
print(f"TOTAL: skipped {tot['skip']}/{tot['arms']} | row a save {tot['save_a']:+.3f} ({tot['skipfills_a']} fills) | row c save {tot['save_c']:+.3f} ({tot['skipfills_c']} fills); runs helped row c: {sum(1 for r in RUNS if res[r]['save_c'] > 1e-9)} hurt {sum(1 for r in RUNS if res[r]['save_c'] < -1e-9)}")
json.dump({r: dict(res[r]) for r in RUNS}, open(f"{OUT}/paper_nbuyers50.json", "w"), indent=1)

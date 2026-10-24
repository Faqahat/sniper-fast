#!/usr/bin/env python3
# What separates a leader's picks from the OTHER launches of the same devs? (read-only, descriptive)
# usage: python3 -I w8_picks.py <work dir with R1/R2 launch/> <w2 out dir> <wallet prefix> [...]
import sys, os, json, gzip, glob, collections, statistics
WORK, OUTD = sys.argv[1], sys.argv[2]; LEAD = sys.argv[3:]
PP = json.load(gzip.open(os.path.join(OUTD, "pairs_cands.json.gz"), "rt"))
LI = {}
for run in ("R1", "R2"):
    for f in glob.glob(os.path.join(WORK, run, "launch", "*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            r = json.loads(l); r["run"] = run; LI[r["m"]] = r
bydev = collections.defaultdict(list)
for m, r in LI.items(): bydev[(r["run"], r["signer"])].append(r)
for k in bydev: bydev[k].sort(key=lambda r: r["bt"] or 0)
def feats(r):
    lst = bydev[(r["run"], r["signer"])]; i = next(k for k, x in enumerate(lst) if x["m"] == r["m"])
    gap = (r["bt"] - lst[i - 1]["bt"]) if i > 0 and r["bt"] and lst[i - 1]["bt"] else None
    return dict(dev_buy=r["dev_buy"] / 1e9, glued_n=r["glued_n"], glued_sol=r["glued_sol"] / 1e9, jito=int(r["jito_n"] > 0), tw=r["tw"], web=r["web"], tg=r["tg"],
                desc=int(r["desc"] > 0), gap_prev_s=gap, idx_in_dev=i, out_buys_slot=r["out_buys_slot"], tool=(r.get("created_on") or "-")[:20],
                name_len=len(r.get("name") or ""), upper=int((r.get("symbol") or "").isupper()))
full = {}
for w in PP:
    if not w.endswith("|fail"): full[w[:8]] = w
for l8 in LEAD:
    w = full[l8]; picks = {p[7] for p in PP[w]}
    devs = {(LI[m]["run"], LI[m]["signer"]) for m in picks if m in LI}
    P = [feats(LI[m]) for m in picks if m in LI]; N = [feats(r) for d in devs for r in bydev[d] if r["m"] not in picks]
    print(f"== {l8}: {len(P)} picks vs {len(N)} other launches of the same {len(devs)} devs")
    for k in ("dev_buy", "glued_n", "glued_sol", "jito", "tw", "web", "tg", "desc", "gap_prev_s", "idx_in_dev", "out_buys_slot", "name_len", "upper"):
        a = [x[k] for x in P if x[k] is not None]; b = [x[k] for x in N if x[k] is not None]
        if a and b: print(f"   {k:14s} picks med {statistics.median(a):8.2f} mean {statistics.mean(a):8.2f} | others med {statistics.median(b):8.2f} mean {statistics.mean(b):8.2f}")
    print("   tools picks", collections.Counter(x["tool"] for x in P).most_common(3), "others", collections.Counter(x["tool"] for x in N).most_common(3))

#!/usr/bin/env python3
# Context (read-only): PnL of ALL snipe pairs (first buy <= 5 slots, not creator / glued / creator-Jito bundle, SOL-quoted,
# no mayhem, no graduated-while-holding) by outside buys ahead and by arrival ms in our feed (R2 from 17:10 UTC).
# Trade-event PnL (bot fees inside txs not included). usage: python3 -I w10_global.py <work dir>
import sys, os, json, gzip, glob, collections
WORK = sys.argv[1]; SH = "/home/moiz/sniper-data/collect/shadow"
OBS = {}
for v in ("scores_v1.jsonl", "scores_v2.jsonl", "scores_v3.jsonl"):
    for l in open(os.path.join(SH, v)):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("type") == "obs" and r["mint"] not in OBS:
            OBS[r["mint"]] = [x.split(":") for x in (r.get("outs") or "-").split(",") if x.count(":") == 3]
def msof(m, w):
    o = OBS.get(m)
    if o is None: return None
    b = next((float(x[0]) for x in o if x[3] == w[:6] and x[2] == "1"), None)
    return b if b is not None else next((float(x[0]) for x in o if x[3] == w[:6]), None)
A = collections.defaultdict(lambda: [0, 0, 0, 0]); M = collections.defaultdict(lambda: [0, 0, 0, 0]); AM = collections.defaultdict(lambda: [0, 0, 0, 0])
def add(d, k, p): x = d[k]; x[0] += 1; x[1] += p["pnl"]; x[2] += p["pnl"] > 0; x[3] += p["bsol"]
for run in ("R1", "R2"):
    for f in glob.glob(os.path.join(WORK, run, "pairs", "*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            p = json.loads(l)
            if p.get("role") or p.get("failed_only") or p.get("fs") is None or p["fs"] > 5 or p["may"] or p["gopen"]: continue
            if p["w"] == "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s": continue
            a = p["ahead"]; ak = "0" if a == 0 else "1-3" if a <= 3 else "4-10" if a <= 10 else "11+"
            add(A, (run, ak), p)
            if run == "R2":
                ms = msof(p["m"], p["w"])
                if ms is not None:
                    mk = "<25" if ms < 25 else "25-50" if ms < 50 else "50-100" if ms < 100 else "100-250" if ms < 250 else "250+"
                    add(M, mk, p)
                    if 50 <= ms < 100: add(AM, ak, p)
f_ = lambda x: f"n={x[0]:6d} pnl={x[1]/1e9:+8.1f} SOL  win={x[2]/max(1,x[0]):.2f}  roi={x[1]/max(1,x[3]):+.4f}"
print("by outside buys ahead (per run):")
for k in ("0", "1-3", "4-10", "11+"):
    print(f"  {k:5s} R1 {f_(A[('R1', k)])} | R2 {f_(A[('R2', k)])}")
print("by arrival ms in our feed (R2 17:10-00:35, launches with engine timelines):")
for k in ("<25", "25-50", "50-100", "100-250", "250+"): print(f"  {k:8s} {f_(M[k])}")
print("arrival 50-100 ms (like us) split by outside buys ahead:")
for k in ("0", "1-3", "4-10", "11+"): print(f"  {k:5s} {f_(AM[k])}")

#!/usr/bin/env python3
# FINAL-2 scored OFFLINE on the feature table (same model, veto, guards and threshold as the live shadow config), to get
# picks in R1 too. R1's first 80% was FINAL-2's TRAINING data (in-sample); its last 20% only served for early stopping
# (nearly unseen); R2 is fully out of sample. Parity check: offline vs live picks on R2.
# usage: python3 -I f2_offline.py  -> f2_off_R1_tail.json (last 20% of R1), f2_off_R2.json
import json, gzip, math
P = "/home/moiz/sniper-data/collect/paper"; CORE = "/home/moiz/sniper/ops/overnight/core"
C = json.load(open("/home/moiz/sniper/ops/shadow/final_config2.json"))
M = json.load(open(f"{P}/{C['model_file']}")); MV = json.load(open(f"{P}/{C['veto_file']}")); THR = M["thresholds"][C["top"]]
src = open("/home/moiz/sniper/ops/shadow/paper_live.py").read()
g = {"math": math, "M": M}; exec(src[src.index("def score(x, M=M):"):src.index("# ---- shadow engine timeline")], g); score = g["score"]
def guard_ok(r):
    if r.get("payer_is_creator") != 1: return False
    if (r.get("glued_n") or 0) == 0 and (r.get("dev_buy") or 0) < 1: return False
    return True
R1, R2 = [], []
for l in gzip.open(f"{P}/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r.get("quote_sol") != 1 or not r.get("bt") or r.get("mayhem"): continue
    (R1 if r["bt"] < 1792645200 else R2).append(r)          # R1 ends 10-22 18:00 PKT (13:00 UTC); R2 starts 20:43 PKT
R1.sort(key=lambda r: (r["bt"], r.get("S") or 0)); cut = R1[int(len(R1) * 0.8)]["bt"]
def picks(rows): return [r["mint"] for r in rows if score(r) >= THR and score(r, MV) < C["veto_cut"] and guard_ok(r)]
p1 = picks([r for r in R1 if r["bt"] >= cut]); p2 = picks(R2)
live = set(json.load(open(f"{CORE}/final2_picks_v3.json")))
json.dump(p1, open(f"{CORE}/f2_off_R1_tail.json", "w")); json.dump(p2, open(f"{CORE}/f2_off_R2.json", "w"))
print(f"R1 SOL launches {len(R1)}; last-20% cut at bt {cut}; offline picks in R1's last 20%: {len(p1)}")
p2s = set(p2); print(f"R2 offline picks {len(p2)}; live picks {len(live)}; both {len(p2s & live)} (offline-only {len(p2s - live)}, live-only {len(live - p2s)})")

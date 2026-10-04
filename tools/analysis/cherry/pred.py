#!/usr/bin/env python3
"""Trigger-prediction accuracy (predicted vs confirmed post-trigger pool state) by venue, and for the triggers of
gated memecoin attempts. usage: pred.py <seg>"""
import json, collections, sys, re
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
def jl(f):
    for l in open(f):
        try: yield json.loads(l)
        except Exception: pass
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None
d = f"/root/arb-lab/runs/{sys.argv[1]}"
Pr = collections.defaultdict(list)
for r in jl(f"{d}/predictions.jsonl"): Pr[r["sig"]].append(r)
def err(r):
    if "err1_bps" in r: return max(abs(r["err0_bps"]), abs(r["err1_bps"]))
    if "pred_active" in r: return abs(r["actual_active"] - r["pred_active"]) * 100.0  # bins -> pseudo bps (x100 per bin)
    return None
by = collections.defaultdict(list)
for rs in Pr.values():
    for r in rs:
        e = err(r)
        if e is not None: by[r["venue"]].append(e)
print("prediction error by venue (PumpSwap/CP: max |reserve err| bps; DLMM: |bin diff|*100):")
for v, e in by.items(): print(f"  {v:9} n={len(e):4} exact={sum(1 for x in e if x < 0.01)/len(e):.0%}  p50={q(e,.5)} p75={q(e,.75)} p90={q(e,.9)}")
T = {t["sig"]: t for t in jl(f"{d}/triggers.jsonl")}
A = {a["attempt"]: a for a in jl(f"{d}/attempts.jsonl")}
P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
rx = re.compile(r"sim_gated .*? \| legs \[(\d+), (\d+)\] predicted \[(\d+), (\d+)\]")
n = collections.Counter(); ex = []
for o in jl(f"{d}/outcomes.jsonl"):
    a = A.get(o["attempt"])
    if not a or a["mint"] == USDC or not rx.match(o.get("settle_error") or ""): continue
    p = P.get(a["opp"]) or {}; s = p.get("trigger")
    t = T.get(s) or {}
    rs = [r for r in Pr.get(s, []) if r["pool"] == p.get("trigger_pool")]
    k = "no prediction record" if not rs else ("prediction exact" if err(rs[0]) < 0.01 else "prediction off")
    n[k] += 1; n[f'trigger exact_out={t.get("exact_out")}'] += 1; n[f'trigger venue={t.get("venue")}'] += 1
    if rs and len(ex) < 12: ex.append((t.get("venue"), t.get("exact_out"), t.get("amount"), {k: v for k, v in rs[0].items() if k in ("err0_bps", "err1_bps", "pred_active", "actual_active")}))
print("gated memecoin attempts' triggers:", dict(n))
for e in ex: print("  ", e)

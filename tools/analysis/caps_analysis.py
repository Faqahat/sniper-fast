#!/usr/bin/env python3
"""exp4: what would a bigger budget add? Per opportunity (caps.jsonl): expected net profit at each budget, joined with
what happened to the gap (opportunities.jsonl: did the trigger land, did someone take the gap, who, how fast; our own
trade's result from attempts/outcomes). Realness tiers:
  all        every opportunity the engine priced
  confirmed  the gap was on confirmed state (state trigger) or its trigger landed on chain (decoded)
  taken      confirmed AND another transaction touched the pools right after (a rival acted on it) or we won it
Outputs per budget tier: opportunities, expected SOL/hour (sum, and median per opportunity), at each realness tier;
per venue pair; top opportunities with their expected profit at every tier. usage: caps_analysis.py <run dir> [SOL usd]"""
import json, sys, os, collections

RUN = sys.argv[1].rstrip("/"); USD = float(sys.argv[2]) if len(sys.argv) > 2 else 119.25
q = lambda v, p: (sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None)
caps = [json.loads(l) for l in open(f"{RUN}/caps.jsonl")]
opps = {}
for l in open(f"{RUN}/opportunities.jsonl"):
    o = json.loads(l); opps[o["id"]] = o
A = {x["opp"]: x for x in map(json.loads, open(f"{RUN}/attempts.jsonl"))} if os.path.exists(f"{RUN}/attempts.jsonl") else {}
O = {x["attempt"]: x for x in map(json.loads, open(f"{RUN}/outcomes.jsonl"))} if os.path.exists(f"{RUN}/outcomes.jsonl") else {}
st = [json.loads(l) for l in open(f"{RUN}/status.jsonl")]
hours = max(1e-9, (st[-1]["t_ns"] - st[0]["t_ns"]) / 3.6e12)
mriya = "MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X"
tiers = [c[0] for c in caps[0]["caps"]] if caps else []

rows = []
for c in caps:
    o = opps.get(c["id"], {})
    att = A.get(c["id"]); out = O.get(att["attempt"]) if att else None
    confirmed = c["kind"] == "state" or bool(o.get("trigger_landed_slot"))
    taker = (o.get("taker") or {}).get("sig")
    we_won = bool(out and out.get("ok"))
    rows.append({"c": c, "confirmed": confirmed, "taken": confirmed and (bool(taker) or we_won), "taker": o.get("taker"), "we_won": we_won,
                 "sent": bool(att), "pair": f'{c["buy_venue"]}>{c["sell_venue"]}'})

def table(sel, label):
    print(f"\n{label}: {len(sel)} opportunities in {hours:.2f} h")
    print("  budget      $        opps>0   expected SOL/h (sum)   median per opp (SOL)   p90 per opp   best size used (SOL, median)")
    for k, cap in enumerate(tiers):
        v = [r["c"]["caps"][k][2] for r in sel if r["c"]["caps"][k][2] is not None]
        pos = [x for x in v if x > 0]
        used = [r["c"]["caps"][k][1] / 1e9 for r in sel if r["c"]["caps"][k][2] is not None and r["c"]["caps"][k][2] > 0]
        print(f"  {cap:>6.3f} SOL ${cap * USD:>7,.0f}  {len(pos):>6}   {sum(pos) / 1e9 / hours:>10.3f}            {(q(pos, .5) or 0) / 1e9:>10.5f}          {(q(pos, .9) or 0) / 1e9:>8.5f}     {q(used, .5) or 0:.3f}")

table(rows, "ALL priced opportunities")
table([r for r in rows if r["confirmed"]], "CONFIRMED (gap on landed state)")
table([r for r in rows if r["taken"]], "TAKEN (a rival acted on it right after, or we won it)")
print("\nTAKEN, by venue pair (expected SOL/h at each budget):")
by = collections.defaultdict(list)
for r in rows:
    if r["taken"]: by[r["pair"]].append(r)
for pair, sel in sorted(by.items(), key=lambda x: -len(x[1])):
    vals = [sum(max(0, r["c"]["caps"][k][2] or 0) for r in sel) / 1e9 / hours for k in range(len(tiers))]
    print(f"  {pair:22} n={len(sel):4}  " + "  ".join(f"${t * USD:,.0f}: {v:.3f}" for t, v in zip(tiers, vals)))
print("\nTop 25 opportunities by expected profit at the largest budget (taken only):")
top = sorted((r for r in rows if r["taken"]), key=lambda r: -(r["c"]["caps"][-1][2] or 0))[:25]
for r in top:
    c = r["c"]
    print(f'  {c["mint"][:8]} {r["pair"]:18} best size {c["best_size"] / 1e9:7.3f} SOL  ' + " ".join(f'{(x[2] or 0) / 1e9:.4f}' for x in c["caps"])
          + f'  taker {((r["taker"] or {}).get("sig") or "")[:8]}{" (WE WON)" if r["we_won"] else ""}')
json.dump([{"id": r["c"]["id"], "kind": r["c"]["kind"], "pair": r["pair"], "mint": r["c"]["mint"], "confirmed": r["confirmed"], "taken": r["taken"],
            "we_won": r["we_won"], "best_size": r["c"]["best_size"], "caps": r["c"]["caps"]} for r in rows], open(f"{RUN}/caps-joined.json", "w"))

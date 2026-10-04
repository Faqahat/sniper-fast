#!/usr/bin/env python3
"""exp4, deduped and checked against what the market really paid. Gap episode = consecutive opportunities on one
(buy pool, sell pool) within 2 s: its expected net at each budget = the max over the episode. Ground truth: rival
arbitrage transactions that moved either pool within 2 s after the episode began (moves.log -> exec.jsonl: signer's
SOL+WSOL gain > 0, no other token left) = profit the market actually took from that gap. usage: caps2.py <run dir>"""
import json, sys, collections
RUN = sys.argv[1].rstrip("/"); USD = 119.25
WSOL = "So11111111111111111111111111111111111111112"
caps = [json.loads(l) for l in open(f"{RUN}/caps.jsonl")]
st = [json.loads(l) for l in open(f"{RUN}/status.jsonl")]
hours = (st[-1]["t_ns"] - st[0]["t_ns"]) / 3.6e12
tiers = [c[0] for c in caps[0]["caps"]]
# episodes
ep = []; last = {}
for c in caps:
    k = (c["buy"], c["sell"])
    e = last.get(k)
    if e and c["slot"] - e["slot_last"] <= 5:
        e["slot_last"] = c["slot"]; e["n"] += 1
        for i, x in enumerate(c["caps"]):
            if x[2] is not None and (e["caps"][i] is None or x[2] > e["caps"][i]): e["caps"][i] = x[2]
    else:
        e = {"buy": c["buy"], "sell": c["sell"], "pair": f'{c["buy_venue"]}>{c["sell_venue"]}', "mint": c["mint"], "slot": c["slot"], "slot_last": c["slot"],
             "n": 1, "caps": [x[2] for x in c["caps"]], "best_size": c["best_size"]}
        ep.append(e); last[k] = e
# rival realized profit per pool per slot
moves = collections.defaultdict(list)
for l in open(f"{RUN}/moves.log"):
    p = l.split()
    if len(p) >= 4: moves[p[2]].append((int(p[1]), p[0]))
want = {s for v in moves.values() for _, s in v}
gain = {}
for l in open(f"{RUN}/exec.jsonl"):
    if '"ok":true' not in l: continue
    x = json.loads(l)
    if x["sig"] not in want: continue
    tok = {k: v for k, v in x["tok"].items() if k != WSOL}
    g = x["sol"] + int(x["tok"].get(WSOL, "0"))
    if g > 0 and not tok: gain[x["sig"]] = (g, x["signer"])
real = []
for e in ep:
    took = {}
    for pool in (e["buy"], e["sell"]):
        for slot, s in moves.get(pool, []):
            if e["slot"] <= slot <= e["slot_last"] + 5 and s in gain: took[s] = gain[s]
    e["rival_sol"] = sum(g for g, _ in took.values()) / 1e9
    e["rivals"] = sorted({w[:8] for _, w in took.values()})
print(f"{len(caps)} priced opportunities -> {len(ep)} gap episodes in {hours:.2f} h")
pos = lambda i, sel: [x["caps"][i] for x in sel if x["caps"][i] and x["caps"][i] > 0]
taken = [e for e in ep if e["rival_sol"] > 0]
print(f"episodes where rivals took real profit: {len(taken)}; rivals took {sum(e['rival_sol'] for e in taken) / hours:.3f} SOL/h from them")
print("\nbudget        | all episodes: our expected SOL/h | episodes rivals monetized: our expected SOL/h | rivals actually took SOL/h")
for i, t in enumerate(tiers):
    a = sum(pos(i, ep)) / 1e9 / hours; b = sum(pos(i, taken)) / 1e9 / hours
    print(f"  ${t * USD:>7,.0f} ({t:>6.3f} SOL) | {a:10.3f} | {b:10.3f} | {sum(e['rival_sol'] for e in taken) / hours:8.3f}")
print("\nper venue pair (episodes rivals monetized): our expected at $20 / $250 / $1k / $10k vs rivals took (SOL/h)")
by = collections.defaultdict(list)
for e in taken: by[e["pair"]].append(e)
idx = {t: i for i, t in enumerate(tiers)}
for pair, sel in sorted(by.items(), key=lambda x: -sum(e["rival_sol"] for e in x[1])):
    g = lambda t: sum(max(0, e["caps"][idx[t]] or 0) for e in sel) / 1e9 / hours
    print(f"  {pair:18} n={len(sel):4}  {g(tiers[0]):.3f} / {g(tiers[1]):.3f} / {g(tiers[3]):.3f} / {g(tiers[-1]):.3f}   rivals {sum(e['rival_sol'] for e in sel) / hours:.3f}")
print("\ntop tokens by rival-realized profit:")
bt = collections.defaultdict(lambda: [0, 0.0, set(), [0.0] * len(tiers)])
for e in taken:
    b = bt[e["mint"]]; b[0] += 1; b[1] += e["rival_sol"]; b[2] |= set(e["rivals"])
    for i in range(len(tiers)): b[3][i] += max(0, e["caps"][i] or 0) / 1e9
for m, b in sorted(bt.items(), key=lambda x: -x[1][1])[:12]:
    print(f"  {m[:8]} episodes {b[0]:4} rivals took {b[1]:.4f} SOL  by {sorted(b[2])[:5]}  our expected $20 {b[3][0]:.4f} / $250 {b[3][1]:.4f} / $1k {b[3][3]:.4f} / $10k {b[3][-1]:.4f}")

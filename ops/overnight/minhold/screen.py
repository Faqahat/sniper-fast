#!/usr/bin/env python3
# MINUTE-HOLD WINNERS (read-only, census parts R1/R2/R3): wallets whose positions are held for minutes and that make >= 10 SOL/day.
# Position = (wallet, mint) on the bonding curve. Hold = first buy -> last sell (slots x 0.212 s). Realized PnL only on closed
# positions (no open tokens left); open positions are counted separately at the last curve price and flagged.
import gzip, glob, json, collections, statistics
HRS = {"R1": 14.88, "R2": 21.79, "R3": 24.0}; SL = 0.212
AGENTS = {"BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"}
W = collections.defaultdict(lambda: collections.defaultdict(list))
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        u, m, run, bt, fb_s, fb_k, fb_sol, spent, got, mark, cost, pnl, nb, ns, ls_s, done, op = json.loads(line)
        if u in AGENTS: continue
        hold = (ls_s - fb_s) * SL / 60 if (ns and ls_s is not None and fb_s is not None) else None
        W[u][run].append((pnl, hold, op, done, spent, fb_s * SL if fb_s is not None else None, nb, ns, bt, mark))
med = lambda v: statistics.median(v) if v else float("nan")
rows = []
for u, runs in W.items():
    r3 = runs.get("R3", [])
    if len(r3) < 15: continue
    tot3 = sum(x[0] for x in r3); day3 = tot3 / HRS["R3"] * 24
    if day3 < 10: continue
    cl = [x for x in r3 if not x[2]]; holds = [x[1] for x in cl if x[1] is not None]
    if not holds: continue
    mh = med(holds)
    t0 = min(x[8] for x in r3); half = [sum(x[0] for x in r3 if (x[8] - t0) < 12 * 3600), sum(x[0] for x in r3 if (x[8] - t0) >= 12 * 3600)]
    oth = {r: sum(x[0] for x in runs.get(r, [])) / HRS[r] * 24 for r in ("R1", "R2") if runs.get(r)}
    rows.append(dict(w=u, n=len(r3), day=day3, real=sum(x[0] for x in cl) / HRS["R3"] * 24, open_n=sum(1 for x in r3 if x[2]), open_pnl=sum(x[0] for x in r3 if x[2]),
                     grad=sum(1 for x in r3 if x[3]), hold=mh, p_min=sum(1 <= h <= 60 for h in holds) / len(holds), win=sum(x[0] > 0 for x in cl) / max(len(cl), 1),
                     size=med([x[4] for x in r3]), entry_s=med([x[5] for x in r3 if x[5] is not None]), nb=med([x[6] for x in r3]), halves=half, other=oth,
                     top5=sum(sorted((x[0] for x in r3), reverse=True)[:5])))
json.dump(rows, open("screen.json", "w"))
print(f"wallets with >= 10 SOL/day in R3 (24 h) and >= 15 positions: {len(rows)}")
print("  of those with median hold 1-60 min:", sum(1 for r in rows if 1 <= r["hold"] <= 60))
print("\nwallet                                       pos  SOL/day realized/day  open(n,SOL) grad  hold-med  %1-60m  win  size  entry(s)  buys  halves(12h)      w/o top5   R1/day  R2/day")
for r in sorted(rows, key=lambda r: -r["day"]):
    if not (1 <= r["hold"] <= 60): continue
    print(f"{r['w']:44s} {r['n']:4d} {r['day']:+7.1f} {r['real']:+8.1f}     {r['open_n']:3d} {r['open_pnl']:+6.1f} {r['grad']:4d} {r['hold']:6.1f}m  {r['p_min']:5.0%} {r['win']:4.0%} {r['size']:5.2f} {r['entry_s']:8.1f} {r['nb']:4.0f}  "
          f"{r['halves'][0]:+6.1f}/{r['halves'][1]:+6.1f}  {(r['day'] * 24 / 24 * HRS['R3'] / 24 - r['top5']) / HRS['R3'] * 24:+7.1f}  {r['other'].get('R1', float('nan')):+7.1f} {r['other'].get('R2', float('nan')):+7.1f}")

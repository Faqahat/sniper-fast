#!/usr/bin/env python3
# Our buys that reverted (pump 6042, the +5% guard) in the 7 h chain recording: what would they have made?
# Curve at our exact block position = the last successful trade on the token before our (slot, idx). Entry: spend S at that curve
# (1.25% fee). Exit: the curve at the last trade <= our slot + HOLD (our buy inserted: reserves +S / -q), 1.25% fee, 0.0016 SOL tx cost.
# (a) guard levels: the buy goes through when price_at_us / post_dump_price <= g. (b) landing at the FIRST pro's position instead of ours.
import json, collections, statistics, bisect
rows = json.load(open("race_rows.json")); B = json.load(open("race_buys.json"))
OURS = ("2g7rYv7y", "EgxfYgEb"); S = 0.35e9; FEE = 0.0125; TXC = 0.0016e9; HOLD = 6
tape = collections.defaultdict(list)      # mint -> [(slot, idx, vsol, vtok)] successful trades
for r in rows:
    if not r[4]: continue
    for t in r[11]: tape[t[0]].append((r[0], r[1], t[5], t[6]))
for m in tape: tape[m].sort()
def state_before(m, s, i):
    v = tape.get(m, []); k = bisect.bisect_left(v, (s, i, -1, -1)) - 1
    return v[k] if k >= 0 else None
def pnl(m, s, i):
    e = state_before(m, s, i)
    if not e: return None
    vs, vt = e[2], e[3]; x = S * (1 - FEE); q = vt * x / (vs + x)
    v = tape[m]; k = bisect.bisect_right(v, (s + HOLD, 10**9, 0, 0)) - 1
    vse, vte = v[k][2], v[k][3]
    if v[k][:2] <= (s, i): vse, vte = vs, vt
    out = (vse + x) * q / (vte) * (1 - FEE)       # sell q into the exit curve with our buy inside
    return (out - S - TXC) / 1e9, vs / vt
res = []
dumps = {(x["s0"], x["dump_i"]): x for x in B}
for x in B:
    if x["who"] != "ours" or x["ok"]: continue          # our reverted buys
    m = None
    # find the mint: the race_buys row lacks it -> look up our failed row at (bs, bi)
    res.append(x)
byk = {(r[0], r[1]): r for r in rows}
out = []
for x in res:
    r = byk.get((x["bs"], x["bi"]))
    if not r: continue
    mints = [m for m in r[10] if m in tape]
    if not mints: continue
    m = mints[0]
    d = state_before(m, x["s0"], x["dump_i"] + 1)        # post-dump state (the dump itself)
    p_us = pnl(m, x["bs"], x["bi"])
    if not d or not p_us: continue
    move = p_us[1] / (d[2] / d[3])
    # first pro's buy on the same dump
    pros = [y for y in B if y["s0"] == x["s0"] and y["dump_i"] == x["dump_i"] and y["who"] == "pro"]
    fp = min(pros, key=lambda y: (y["bs"], y["bi"])) if pros else None
    p_pro = pnl(m, fp["bs"], fp["bi"]) if fp else None
    out.append(dict(cl=x["cl"], move=move, pnl=p_us[0], pnl_at_pro=p_pro[0] if p_pro else None, same=x["same"]))
print(f"our reverted buys analysed: {len(out)}")
print(f"price at our position vs post-dump price: median x{statistics.median([o['move'] for o in out]):.3f}")
for g in (1.10, 1.15, 1.25, 9.9):
    v = [o for o in out if o["move"] <= g]
    print(f"  guard {'off' if g > 9 else f'+{(g-1)*100:.0f}%'}: {len(v)} of {len(out)} would fill | total {sum(o['pnl'] for o in v):+.3f} SOL | per fill {sum(o['pnl'] for o in v)/max(len(v),1):+.4f} | winners {sum(1 for o in v if o['pnl']>0)}")
w = [o for o in out if o["pnl_at_pro"] is not None]
print(f"  landing at the FIRST pro's position instead: {len(w)} buys | total {sum(o['pnl_at_pro'] for o in w):+.3f} SOL | per buy {sum(o['pnl_at_pro'] for o in w)/max(len(w),1):+.4f} | winners {sum(1 for o in w if o['pnl_at_pro']>0)}")
for cl in sorted({o["cl"] for o in out}):
    v = [o for o in out if o["cl"] == cl]
    print(f"    {cl:20s} n={len(v):3d} | move median x{statistics.median([o['move'] for o in v]):.3f} | at our spot no guard {sum(o['pnl'] for o in v):+.3f} | at first pro {sum(o['pnl_at_pro'] or 0 for o in v):+.3f}")

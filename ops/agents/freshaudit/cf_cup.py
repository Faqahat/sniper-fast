#!/usr/bin/env python3
# BAM/Harmonic blocks order each arrival batch by priority fee (cup). Batch of our tx = run of recorded txs (any mint)
# ending at our tx in which cup is non-increasing; with a cup above X we would move ahead of every tx in that run with cup < X.
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from load import *
from sim import *
A = "/home/moiz/sniper/ops/agents/freshaudit"
FC = [x for x in json.load(open(f"{A}/out/fire_chain.json")) if "dump" in x and "ours" in x]
fires = json.load(open(f"{A}/out/fires.json"))
TP = load_tapes(f"{A}/out/tapes_live.json.gz")
t0 = int(min(f["t"] for f in fires)) - 400; t1 = int(max(f["t"] for f in fires)) + 60
L = load("r3", t0, t1, kinds=("F",))
byslot = collections.defaultdict(list)
for r in L["F"].values(): byslot[r["s"]].append(r)
for s in byslot: byslot[s].sort(key=lambda r: r["i"])
res = collections.defaultdict(lambda: [0, 0, 0.0]); detail = []
for f in FC:
    cl = f["client"] or ""
    kind = "bam" if ("Bam" in cl or "BAM" in cl) else "harmonic" if "Harmonic" in cl else "other"
    d = f["dump"]; o = f["ours"]
    rows = TP[f["mint"]]; tr = trades(rows, drop_user=OURS)
    for t in trades(rows):
        if (t[0], t[1]) == (d["s"], d["i"]) and t[3] == 0: dst = (t[7], t[8]); fr = (t[9] + t[10]) / 1e4
    blk = [r for r in byslot.get(o["s"], []) if r["i"] < o["i"]]
    # walk back: batch continues while cup (as recorded; None->0) is >= ours and non-decreasing backwards
    our_cup = o["cup"] or 0; prev = our_cup; start = o["i"]; ahead = []
    for r in reversed(blk):
        c = r["cup"] or 0
        if c < prev: break
        ahead.append(c); start = r["i"]; prev = c
    if o["s"] == d["s"]: start = max(start, d["i"] + 1)
    for X in (5_000_000, 10_000_000, 20_000_000, 50_000_000, 100_000_000):
        pos = (o["s"], o["i"])
        if kind in ("bam", "harmonic"):
            # we pass every tx of our batch whose cup < X -> our new index = first tx in batch with cup >= X (from the front)
            new_i = o["i"]
            for r in [r for r in blk if r["i"] >= start]:
                if (r["cup"] or 0) < X: new_i = r["i"]; break
            pos = (o["s"], new_i)
        x = simulate(tr, pos, dst, f["spend"] / 1e9, guard=1.05, exit_mode=("time", 5, 100), fr=fr, tip=f["tips"])
        extra = (X - 5_000_000) * 100_000 / 1e15   # extra priority SOL per attempt at a 100k CU limit
        k = (kind if kind != "other" else "jito/fd/other", X); res[k][0] += 1; res[k][1] += x["fill"]; res[k][2] += x["pnl_net"] - extra
    detail.append(dict(mint=f["mint"][:6], kind=kind, res=f["result"], batch_ahead=len(ahead), ahead_cups=[round(c / 1e6, 1) for c in reversed(ahead)]))
print("replay of the 68 fires (time exit), net incl. the extra priority fee at a 100k CU limit:")
for k in sorted(res):
    v = res[k]; print(f"  {k[0]:<15} cup={k[1]/1e6:>5.0f}M  fires {v[0]:>2} fills {v[1]:>2}  net {v[2]:+.3f}")
for x in detail:
    if x["kind"] != "other" and x["batch_ahead"]: print("  ", x)

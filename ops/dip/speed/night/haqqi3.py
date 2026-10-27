import json, pickle, collections, bisect, statistics
exec(open("replay_hq.py").read().split("hours = ")[0])
trips = pickle.load(open("haqqi_trips.pkl", "rb"))
med = lambda v: round(statistics.median(v), 3) if v else None
# his entry position after the dump (same slot: txs after the big sell)
d = [t for t in trips if t["after_dump"]]
same = [t for t in d if t["same_slot_dump"]]
print(f"his dump trips {len(d)} | same slot as the dump {len(same)/len(d):.0%}")
# replay HIS entries with a fixed exit vs his real P&L
res = collections.defaultdict(list)
for t in d:
    v = T.get(t["m"]); 
    if not v: continue
    keys = [(x[0], x[1]) for x in v]
    k = bisect.bisect_left(keys, (t["s"], t["i"]))
    for hold in (3, 6, 9):
        ke = k - 1
        if ke < 0: continue
        ev = v[ke]; x = 0.3e9 * (1 - FEE); q = ev[7] * x / (ev[6] + x)
        kx = bisect.bisect_left(keys, (t["s"] + hold + 1, 0)) - 1; xv = v[kx]
        out = (xv[6] + x) * q / xv[7] * (1 - FEE); res[hold].append((out - 0.3e9) / 1e9 - 0.002)
    res["his real (scaled to 0.3 SOL, minus 2.5% fees + 0.002)"].append(t["pnl"] * 0.3 / t["sol"] - 0.3 * 0.025 - 0.002)
for k, v in res.items(): print(f"  his entries, exit {k}: n={len(v)} total {sum(v):+.2f} per trade {sum(v)/len(v):+.4f} win {sum(1 for x in v if x>0)/len(v):.0%}")

import json, pickle, collections, bisect, statistics
exec(open("replay_hq.py").read().split("hours = ")[0])
trips = pickle.load(open("haqqi_trips.pkl", "rb"))
d = [t for t in trips if t["after_dump"]]
# his dump = the last >= 1 SOL sell on the token before his buy (<= 10 slots)
out = collections.defaultdict(list); his_off = []
for t in d:
    v = T.get(t["m"])
    if not v: continue
    keys = [(x[0], x[1]) for x in v]; k = bisect.bisect_left(keys, (t["s"], t["i"]))
    dump = next((v[j] for j in range(k - 1, -1, -1) if not v[j][3] and v[j][4] >= 1e9 and v[j][0] >= t["s"] - 10), None)
    if not dump: continue
    if dump[0] == t["s"]: his_off.append(t["i"] - dump[1])
    for off in (0, 20, 40, 80):
        for hold in (6, 9):
            p = replay(v, dump[0], dump[1], off, hold)
            if p is not None: out[(off, hold)].append(p)
print(f"his entry when in the dump's slot: median {statistics.median(his_off)} txs after the dump (p25 {sorted(his_off)[len(his_off)//4]}, p75 {sorted(his_off)[3*len(his_off)//4]})")
for (off, hold), v in sorted(out.items()):
    print(f"  HIS dumps, entry +{off:2d} txs, hold {hold}: n={len(v)} total {sum(v):+.2f} SOL per trade {sum(v)/len(v):+.4f} (20% follower cut, +5% guard)")

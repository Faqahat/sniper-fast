import json, pickle, collections, statistics, bisect
trips = pickle.load(open("haqqi_trips.pkl", "rb")); rows = json.load(open("race_rows.json"))
med = lambda v: round(statistics.median(v), 3) if v else None
d = [t for t in trips if t["after_dump"]]
# ---- selection: all >= 1 SOL dumps in the window vs those haqqi bought after (<= 10 slots)
T = collections.defaultdict(list); first = {}
for r in rows:
    if not r[4]: continue
    for t in r[11]:
        if 25e9 <= t[5] <= 200e9: T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2], t[5], t[6])); first.setdefault(t[0], r[0])
taken = {(t["m"]) for t in d}
hq = collections.defaultdict(list)
for t in d: hq[t["m"]].append(t["s"])
D = []
for m, v in T.items():
    v.sort(); slots = [x[0] for x in v]
    for k, x in enumerate(v):
        if x[3] or x[4] < 1e9: continue
        s = x[0]; a15 = bisect.bisect_left(slots, s - 70); a5 = bisect.bisect_left(slots, s - 24)
        pre = v[k - 1] if k else x
        drop = 1 - (x[6] / x[7]) / ((x[6] + x[4]) / max(x[7] - x[5], 1))
        took = any(s <= hs <= s + 10 for hs in hq.get(m, []))
        D.append(dict(took=took, sell=x[4] / 1e9, drop=drop, curve=x[6] / 1e9, age=(s - first[m]) * 0.2126, flow15=sum(y[4] for y in v[a15:k] if y[3]) / 1e9,
                      buyers5=len({y[2] for y in v[a5:k] if y[3]})))
print(f"dumps >= 1 SOL: {len(D)} | haqqi bought after {sum(x['took'] for x in D)} ({sum(x['took'] for x in D)/len(D):.1%})")
for f, edges in (("sell", [1, 1.5, 2, 3, 5, 10, 999]), ("drop", [0, .03, .06, .1, .15, .25, 1]), ("curve", [25, 35, 45, 60, 80, 200]), ("age", [0, 10, 30, 60, 300, 1800, 1e9]), ("flow15", [0, 2, 5, 10, 25, 1e9]), ("buyers5", [0, 2, 5, 10, 20, 999])):
    parts = []
    for lo, hi in zip(edges, edges[1:]):
        v = [x for x in D if lo <= x[f] < hi]
        if v: parts.append(f"{lo}-{hi}: {sum(x['took'] for x in v)/len(v):.0%} of {len(v)}")
    print(f"  take rate by {f:8s}: " + " | ".join(parts))
# ---- his P&L by the same features (dump trips only)
print("\nhis dump trips: P&L per trip by feature bucket")
for f, edges in (("dump_sol", [1, 1.5, 2, 3, 5, 999]), ("age", [0, 10, 30, 60, 300, 1e9]), ("curve", [25, 35, 45, 60, 200]), ("ch15", [-1, -.2, -.1, -.05, 0, .1, 9]), ("buyers5", [0, 2, 5, 10, 20, 999]), ("hold", [0, 1, 2, 3, 5, 10, 999])):
    parts = []
    for lo, hi in zip(edges, edges[1:]):
        v = [t for t in d if t[f] is not None and lo <= t[f] < hi]
        if v: parts.append(f"{lo}-{hi}: {sum(t['pnl'] for t in v)/len(v):+.4f} (n={len(v)}, win {sum(t['pnl']>0 for t in v)/len(v):.0%})")
    print(f"  {f:8s}: " + " | ".join(parts))

#!/usr/bin/env python3
# One wallet's behaviour on the 7 h chain (READ-ONLY): every buy -> context just before it, its round trip, and P&L.
import json, collections, statistics, bisect, sys
W = sys.argv[1]; rows = json.load(open("race_rows.json"))
T = collections.defaultdict(list); first = {}; mine = collections.Counter()
for r in rows:
    if r[3] == W: mine["ok" if r[4] else "failed"] += 1; [mine.update([("tip", t[0])]) for t in r[7]]
    if r[4]:
        for t in r[11]:
            if 25e9 <= t[5] <= 200e9: T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2], t[5], t[6], r[5], r[6])); first.setdefault(t[0], r[0])
med = lambda v: round(statistics.median(v), 3) if v else None
trips = []
for m, v in T.items():
    v.sort(); slots = [x[0] for x in v]
    for k, x in enumerate(v):
        if x[2] != W or not x[3]: continue
        s = x[0]; a15 = bisect.bisect_left(slots, s - 70); a2 = bisect.bisect_left(slots, s - 10)
        prev = v[k - 1] if k else None
        gap = (s - prev[0]) * 0.2126 if prev else None
        bigsell = any(not y[3] and y[4] >= 1e9 for y in v[a2:k])
        buys_before = sum(1 for y in v[:k] if y[3])
        sell = next((y for y in v[k + 1:] if y[2] == W and not y[3]), None)
        mid = [y for y in v[k + 1:] if sell and (y[0], y[1]) < (sell[0], sell[1])]
        t = dict(sol=x[4] / 1e9, age=(s - first[m]) * 0.2126, curve=x[6] / 1e9, gap=gap, after_bigsell=bigsell, flow15=sum(y[4] for y in v[a15:k] if y[3]) / 1e9,
                 nbuys_before=buys_before, first_in_slot=not any(y[0] == s for y in v[:k]), cup=x[8], cul=x[9])
        if sell:
            f = min(1.0, x[5] / sell[5]) if sell[5] else 0
            t.update(hold=(sell[0] - s) * 0.2126, pnl=sell[4] * f / 1e9 - x[4] / 1e9 * (f * sell[5] / x[5]), followers=len({y[2] for y in mid if y[3]}), follow_sol=sum(y[4] for y in mid if y[3]) / 1e9)
        trips.append(t)
w = [t for t in trips if "pnl" in t]; hours = (rows[-1][0] - rows[0][0]) * 0.2126 / 3600
vol = sum(t["sol"] for t in w)
print(f"{W}\n txs: {dict((k, v) for k, v in mine.items() if k in ('ok','failed'))} | tips by service: {[(k[1], v) for k, v in mine.items() if isinstance(k, tuple)]}")
print(f" buys {len(trips)} ({len(trips)/hours:.0f}/h) | round trips {len(w)} | size median {med([t['sol'] for t in trips])} SOL | hold median {med([t['hold'] for t in w])} s (p25 {sorted(t['hold'] for t in w)[len(w)//4]:.2f}, p75 {sorted(t['hold'] for t in w)[3*len(w)//4]:.2f})")
print(f" curve P&L {sum(t['pnl'] for t in w):+.2f} SOL | minus pump fees 2.5% ({vol*0.025:.2f}) = {sum(t['pnl'] for t in w)-vol*0.025:+.2f} SOL in {hours:.1f} h | win {sum(t['pnl']>0 for t in w)/len(w):.0%} | per trip {sum(t['pnl'] for t in w)/len(w):+.4f}")
print(f" entry context: token age median {med([t['age'] for t in trips])} s | curve median {med([t['curve'] for t in trips])} SOL | after a >=1 SOL sell (<=2 s) {sum(t['after_bigsell'] for t in trips)/len(trips):.0%}"
      f" | gap since the token's previous trade median {med([t['gap'] for t in trips if t['gap'] is not None])} s | flow last 15 s median {med([t['flow15'] for t in trips])} SOL | buys before it on the token median {med([t['nbuys_before'] for t in trips])}")
print(f" while it holds: other buyers median {med([t['followers'] for t in w])}, their SOL median {med([t['follow_sol'] for t in w])} | CU price median {med([t['cup'] for t in trips if t['cup']])}, CU limit median {med([t['cul'] for t in trips if t['cul']])}")
for name, f in (("quiet token (gap >= 3 s)", lambda t: t["gap"] is not None and t["gap"] >= 3), ("busy token (gap < 3 s)", lambda t: t["gap"] is not None and t["gap"] < 3),
                ("after a big sell", lambda t: t["after_bigsell"]), ("young (<= 30 s)", lambda t: t["age"] <= 30), ("older (> 60 s)", lambda t: t["age"] > 60)):
    v = [t for t in w if f(t)]
    if v: print(f"   {name:26s} n={len(v):4d} | per trip {sum(t['pnl'] for t in v)/len(v):+.4f} | after fees {(sum(t['pnl'] for t in v) - sum(t['sol'] for t in v)*0.025)/len(v):+.4f} | win {sum(t['pnl']>0 for t in v)/len(v):.0%} | followers median {med([t['followers'] for t in v])}")

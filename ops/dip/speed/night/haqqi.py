#!/usr/bin/env python3
# haqqiUUX deep dive (7 h chain, READ-ONLY): every buy -> its context (what happened on the token just before) and its round trip.
import json, collections, statistics, bisect, pickle
rows = json.load(open("race_rows.json")); W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
T = collections.defaultdict(list); first = {}
for r in rows:
    if not r[4]: continue
    for t in r[11]:
        if 25e9 <= t[5] <= 200e9:
            T[t[0]].append((r[0], r[1], t[4], t[3], t[1], t[2], t[5], t[6], r[7], r[5], r[6]))
            first.setdefault(t[0], r[0])
trips = []
for m, v in T.items():
    v.sort(); slots = [x[0] for x in v]
    for k, x in enumerate(v):
        s, i, u, buy, sol, tok, vsol, vtok, tips, cup, cul = x
        if u != W or not buy or sol < 1e7: continue
        a15 = bisect.bisect_left(slots, s - 70); a5 = bisect.bisect_left(slots, s - 24); a2 = bisect.bisect_left(slots, s - 10)
        prev = v[a15:k]
        bigsell = [y for y in v[a2:k] if not y[3] and y[4] >= 1e9]          # >= 1 SOL sell in the last ~2 s
        last = v[k - 1] if k else None
        p_now = vsol / vtok
        p_15 = (v[a15][6] / v[a15][7]) if a15 < k else p_now
        sell = next((y for y in v[k + 1:] if y[2] == u and not y[3]), None)
        if not sell: continue
        frac = min(1.0, tok / sell[5]) if sell[5] else 0
        pnl = sell[4] * frac / 1e9 - sol / 1e9 * (frac * sell[5] / tok)
        # what happened between buy and sell: big sells by others? price at sell vs buy
        mid = [y for y in v[k + 1:] if (y[0], y[1]) < (sell[0], sell[1])]
        trips.append(dict(m=m, s=s, i=i, sol=sol / 1e9, hold=(sell[0] - s) * 0.2126, pnl=pnl, age=(s - first[m]) * 0.2126,
            curve=vsol / 1e9, flow15=sum(y[4] for y in prev if y[3]) / 1e9, sells15=sum(y[4] for y in prev if not y[3]) / 1e9,
            buyers5=len({y[2] for y in v[a5:k] if y[3]}), ch15=p_now / p_15 - 1, after_dump=bool(bigsell),
            dump_sol=max((y[4] for y in bigsell), default=0) / 1e9, dump_gap=((s - bigsell[-1][0]) * 212.6 + 0) if bigsell else None,
            same_slot_dump=any(y[0] == s for y in bigsell), n_between=len(mid), bigsell_between=any(not y[3] and y[4] >= 1e9 for y in mid),
            tips=[t[0] for t in tips], cup=cup, cul=cul, sell_hold_slots=sell[0] - s))
pickle.dump(trips, open("haqqi_trips.pkl", "wb"))
med = lambda v: round(statistics.median(v), 3) if v else None
print(f"haqqiUUX round trips (SOL curves): {len(trips)} in 7 h ({len(trips)/7:.0f}/h) | total P&L {sum(t['pnl'] for t in trips):+.2f} SOL (before tx fees/tips) | win {sum(t['pnl']>0 for t in trips)/len(trips):.0%}")
print(f"size median {med([t['sol'] for t in trips])} SOL | hold median {med([t['hold'] for t in trips])} s (p25 {sorted(t['hold'] for t in trips)[len(trips)//4]:.2f}, p75 {sorted(t['hold'] for t in trips)[3*len(trips)//4]:.2f})")
for name, f in (("after a >=1 SOL sell (<=2 s before)", lambda t: t["after_dump"]), ("  ...in the SAME slot as that sell", lambda t: t["same_slot_dump"]), ("no big sell before (flow/other)", lambda t: not t["after_dump"])):
    v = [t for t in trips if f(t)]
    print(f"  {name:38s} n={len(v):4d} ({len(v)/len(trips):.0%}) | P&L {sum(t['pnl'] for t in v):+.2f} | per trip {sum(t['pnl'] for t in v)/max(len(v),1):+.4f} | win {sum(t['pnl']>0 for t in v)/max(len(v),1):.0%} | hold {med([t['hold'] for t in v])} s")

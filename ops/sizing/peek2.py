import json, collections
S = json.load(open("/root/sizing/sells.json"))
by = collections.defaultdict(list)
for s in S: by[s["mint"]].append(s)
n = 0
for m, ss in by.items():
    if not ss[0]["in_tape"]: continue
    n += 1
    if n > 40: break
    print(m[:6], " | ".join(f"d{s['dslot']}/{s['dt']}s f{s['frac']:.2f} px{s['px_vs_entry']:.2f} pk{(s.get('peak_since') or 0):.2f} b2:{s.get('buy_sol_2',0)/1e9:.1f} mb1:{s.get('max_buy_1',0)/1e9:.1f} s2:{s.get('sell_sol_2',0)/1e9:.1f} bs:{s.get('bundle_sold_since',0)/1e9:.1f} gap{s.get('last_ev_slot_gap')} {'B' if (s.get('last_ev') or [0])[0] else 'S'}{(s.get('last_ev') or [0,0,0])[2]/1e9:.1f} ix{''.join(x[0] for x in s['ixs'])}" for s in ss))
c = collections.Counter(round(s["frac"], 2) for s in S); print(c.most_common(15))
c = collections.Counter((s["leg"], round(s["frac"], 2)) for s in S); print(sorted(c.items(), key=lambda x: -x[1])[:25])

import json, sys, collections
W = json.load(open("work/pass1.json"))
rows = []
for w, a in W.items():
    if a["nbd"] < 20 or a["nb"] > 100000: continue
    ffd = a["ff"] * a["nbd"] / max(a["nb"], 1)
    cons = a["pnld"] + a["mtmdneg"] - ffd          # conservative: open dip lots count only their losses
    rows.append((cons / 1e9, w, a, ffd))
rows.sort(key=lambda x: -x[0])
print(f"{'wallet':45s} {'consD':>7s} {'realD':>7s} {'mtm-':>6s} {'mtm':>6s} {'ffD':>5s} {'nbd':>5s} {'dsh':>4s} {'win%':>5s} {'avgB':>5s} {'nfail':>7s} {'hrs+':>5s} {'day':>6s} {'night':>6s} {'1st%':>5s} {'ds0':>4s} {'ds1':>4s} {'ds2-5':>5s} {'tip%':>5s}")
for cons, w, a, ffd in rows[:40]:
    hrs = a["hd"]; pos_h = sum(1 for v in hrs.values() if v > 0)
    ds = {int(k): v for k, v in a["ds"].items()}
    print(f"{w:45s} {cons:7.2f} {a['pnld']/1e9:7.2f} {a['mtmdneg']/1e9:6.2f} {a['mtmd']/1e9:6.2f} {ffd/1e9:5.2f} {a['nbd']:5d} {a['nbd']/a['nb']:4.2f} {100*a['winsd']/max(a['lotsd'],1):5.1f} {a['solbd']/a['nbd']/1e9:5.2f} {a['nf']:7d} {pos_h:2d}/{len(hrs):2d} {a['day']/1e9:6.2f} {a['night']/1e9:6.2f} {100*a['first']/a['nbd']:5.1f} {ds.get(0,0):4d} {ds.get(1,0):4d} {sum(v for k,v in ds.items() if k>=2):5d} {100*a['nbtip']/a['nb']:5.1f}")
json.dump([(w, cons) for cons, w, a, ffd in rows[:300]], open("work/rank3.json", "w"))
# prefix clusters
pre = collections.defaultdict(list)
for cons, w, a, ffd in rows:
    pre[w[:5]].append((w, cons))
print()
for p, l in pre.items():
    if len(l) > 1 and sum(c for _, c in l) > 5: print(p, len(l), round(sum(c for _, c in l), 2), [x[0][:10] for x in l[:8]])

import json, sys, collections
W = json.load(open("work/pass1.json"))
rows = []
for w, a in W.items():
    if a["nbd"] < 20: continue
    # net on dip lots: realized + MTM of open dip lots - failed-tx fees pro-rata (by dip share of buys)
    ffd = a["ff"] * a["nbd"] / max(a["nb"], 1)
    netd = a["pnld"] + a["mtmd"] - ffd
    neta = a["pnl"] + a["mtm"] - a["ff"]
    rows.append((netd / 1e9, w, a, ffd, neta))
rows.sort(key=lambda x: -x[0])
print(f"{'wallet':45s} {'netDip':>7s} {'realD':>7s} {'mtmD':>7s} {'netAll':>7s} {'nbd':>5s} {'nb':>5s} {'dsh':>4s} {'win%':>5s} {'avgB':>5s} {'nfail':>7s} {'ffee':>6s} {'hrs+':>5s} {'opn':>4s} {'ds0':>4s} {'ds1':>4s} {'ds2+':>4s} {'tip%':>5s}")
for netd, w, a, ffd, neta in rows[:45]:
    hrs = a["hd"]; pos_h = sum(1 for v in hrs.values() if v > 0)
    ds = {int(k): v for k, v in a["ds"].items()}
    print(f"{w:45s} {netd:7.2f} {a['pnld']/1e9:7.2f} {a['mtmd']/1e9:7.2f} {neta/1e9:7.2f} {a['nbd']:5d} {a['nb']:5d} {a['nbd']/a['nb']:4.2f} {100*a['winsd']/max(a['lotsd'],1):5.1f} {a['solbd']/a['nbd']/1e9:5.2f} {a['nf']:7d} {a['ff']/1e9:6.2f} {pos_h:2d}/{len(hrs):2d} {a['nopend']:4d} {ds.get(0,0):4d} {ds.get(1,0):4d} {sum(v for k,v in ds.items() if k>=2):4d} {100*a['nbtip']/a['nb']:5.1f}")
json.dump([(w, netd, neta/1e9) for netd, w, a, ffd, neta in rows[:200]], open("work/rank2.json", "w"))

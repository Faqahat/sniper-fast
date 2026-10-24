import json, sys, collections
W = json.load(open("work/pass1.json"))
rows = []
for w, a in W.items():
    if a["nbd"] < 20: continue
    net = a["pnld"] - (a["ff"] * a["nbd"] / max(a["nb"], 1))   # failed fees pro-rata to dip share of buys
    hrs = a["hd"]
    pos_h = sum(1 for v in hrs.values() if v > 0); nh = len(hrs)
    rows.append((a["pnld"] / 1e9, w, a))
rows.sort(key=lambda x: -x[0])
print(f"{'wallet':45s} {'pnl_dip':>8s} {'pnl_all':>8s} {'nbd':>5s} {'nb':>5s} {'dipshare':>6s} {'lotsd':>5s} {'win%':>5s} {'avgB':>6s} {'fail':>6s} {'failfee':>7s} {'hrs+':>5s} {'openD':>6s} {'unm':>4s} {'ds0':>4s} {'ds1':>4s} {'ds2+':>4s} {'tip%':>5s} R2/R3")
for pn, w, a in rows[:60]:
    hrs = a["hd"]; pos_h = sum(1 for v in hrs.values() if v > 0)
    ds = {int(k): v for k, v in a["ds"].items()}
    print(f"{w:45s} {pn:8.2f} {a['pnl']/1e9:8.2f} {a['nbd']:5d} {a['nb']:5d} {a['nbd']/a['nb']:6.2f} {a['lotsd']:5d} {100*a['winsd']/max(a['lotsd'],1):5.1f} {a['solbd']/a['nbd']/1e9:6.2f} {a['nf']:6d} {a['ff']/1e9:7.3f} {pos_h:2d}/{len(hrs):2d} {a['opencd']/1e9:6.2f} {a['unm']:4d} {ds.get(0,0):4d} {ds.get(1,0):4d} {sum(v for k,v in ds.items() if k>=2):4d} {100*a['nbtip']/a['nb']:5.1f} {a['runs']}")

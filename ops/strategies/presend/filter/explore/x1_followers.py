#!/usr/bin/env python3
"""EXPLORATION (dev only, AMS r24+r25): who are the followers in our pre-send fills? Were they active on the token before the trigger?
Uses the exact replay's data (replay065: pos_cal.pkl, tape.pkl). Prints tables only."""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core
D = core.Data()
PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
coh = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
cw = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_cw.json")))
OUR = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"; FRA = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
RENT = 1_508_820
rows = []
fol_cnt = collections.Counter(); fol_win = collections.Counter()
for p in PS:
    T = D.tape[p.mint]["trades"]
    trig = p.trig
    between = [r for r in p.rows if r["kind"] == "trade" and (r["s"], r["i"]) < p.sell_pos]
    users_b = [r["user"] for r in between]
    pre = [t for t in T if (t["s"], t["i"]) < (trig["slot"], trig["idx"])]
    pre_users = set(t["user"] for t in pre)
    net = p.realized + RENT
    flat = len(between) > 0 and abs(net) < 0.004e9
    d = dict(run=p.run, mint=p.mint[:8], net=net / 1e9, nb=len(between), nbuy=sum(1 for r in between if r["tr"]["buy"]),
             coh_b=len(set(u for u in users_b if u in coh)), cw_b=len(set(u for u in users_b if u in cw)),
             pre_n=len(pre), pre_coh=len(pre_users & coh), pre_cw=len(pre_users & cw), fol_pre=len(set(users_b) & pre_users),
             fol_n=len(set(users_b)), why=p.exit_why, whale=trig["wallet"][:8], pct=trig["pct"], age=trig["age_slots"], vsol=trig["vsol"] / 1e9)
    rows.append(d)
    for u in set(users_b):
        fol_cnt[u] += 1
        if net > 0: fol_win[u] += 1
def tab(sel, name):
    X = [r for r in rows if sel(r)]
    print(f"{name:28s} n={len(X):4d} net={sum(r['net'] for r in X):+.3f}  mean nb={np.mean([r['nb'] for r in X]):.1f} pre_n={np.mean([r['pre_n'] for r in X]):.1f} pre_coh={np.mean([r['pre_coh'] for r in X]):.2f} pre_cw={np.mean([r['pre_cw'] for r in X]):.2f} coh_b={np.mean([r['coh_b'] for r in X]):.2f} fol_pre/fol_n={sum(r['fol_pre'] for r in X)}/{sum(r['fol_n'] for r in X)}")
tab(lambda r: True, "all")
tab(lambda r: r["nb"] == 0, "no-trade")
tab(lambda r: r["nb"] > 0 and r["net"] <= 0, "traded, lost")
tab(lambda r: r["net"] > 0, "won")
print("followers seen in >=5 fills:", [(u[:8], c, fol_win[u], u in coh, u in cw) for u, c in fol_cnt.most_common(40) if c >= 5])
# whales
wc = collections.Counter(r["whale"] for r in rows)
print("repeat whales:", [(w, c, round(sum(r['net'] for r in rows if r['whale'] == w), 3)) for w, c in wc.most_common(15)])
# distribution of net
nets = np.array([r["net"] for r in rows])
print("net pcts", np.percentile(nets, [5, 10, 25, 50, 75, 90, 95]).round(4), "wins", (nets > 0).sum(), "of", len(nets))
print("n between: no-trade", sum(1 for r in rows if r['nb'] == 0), " |net|<0.004 & traded", sum(1 for r in rows if r['nb'] > 0 and abs(r['net']) < 0.004))
json.dump(rows, open("/home/moiz/sniper-data/presend_filter/x1_rows.json", "w"))

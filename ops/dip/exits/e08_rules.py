#!/usr/bin/env python3
# e08: "hold the winners only when the crowd is there" rule families, chosen on TRAIN, reported on TEST and on our real live fills.
# CROWDHOLD(c, kq, kmin, m, b, cap): at the start of each slot k after our buy (features = trades our feed saw before that slot):
#   crowd = distinct fast dip bots (75-bot list) that bought since the dump (seen on the feed, incl. before our buy)
#   - crowd < c  (quiet):   sell at tick kq
#   - crowd >= c (crowded): from tick kmin, sell at the first tick whose last m slots had no outside buy >= b SOL (b = 0: no buy at all)
#   - forced sell at tick cap
# Selection: engine SOL/day on TRAIN, M2 + IMIT1 picks, our measured landing; ties broken by the simpler rule.
# -> /home/moiz/sniper-data/exits/e08_rules.json/.txt
import sys, os, json, time, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e03_baselines as B

OUT = f"{E.DATA}/e08_rules"


def crowdhold(d, c, kq, kmin, m, b, cap):
    F = d.ft; I = d.TFI; K = d.K
    crowd = F[:, :, I["tg_dump"]]
    if m == 1: bs = F[:, :, I["bsol1"]]; nb = F[:, :, I["nb1"]]
    else: bs = F[:, :, I["bsol2"]]; nb = F[:, :, I["nb2"]]
    stall = (nb == 0) if b <= 0 else (bs < b)
    ks = np.arange(1, K + 1)[None, :]
    sell = ((crowd < c) & (ks >= kq)) | ((crowd >= c) & (ks >= kmin) & stall) | (ks >= cap)
    k = sell.argmax(1) + 1
    return d.tick_policy(k)


def score(d, pol, periods, which=("M2", "IMIT1"), lmode="meas", R=12):
    val, tdec, knd = pol
    pnl = d.pnl(val, 0)
    out = {}
    for pn, per in periods.items():
        for w in which:
            e = d.engine(d.picks(w), pnl, tdec, knd, lmode=lmode, R=R, period=per)
            out[f"{w}_{pn}"] = V.fmt_day(e["pnl"], per)
    return out


if __name__ == "__main__":
    T0 = time.time()
    d = V.Data(); D = d.D
    PER = {"train": (V.W0, V.SPLIT), "tr1": (V.W0, V.VAL0), "val": (V.VAL0, V.SPLIT)}
    grid = list(itertools.product((1, 2, 3, 4, 5), (1, 2, 3, 4), (2, 3, 4), (1, 2), (0.0, 0.2, 0.5), (9, 12, 19, 30)))
    grid = [g for g in grid if g[5] > g[2]]
    res = {}
    for i, g in enumerate(grid):
        res[str(g)] = score(d, crowdhold(d, *g), PER)
        if (i + 1) % 200 == 0: print(f"  {i + 1}/{len(grid)} rules, {time.time() - T0:.0f} s", flush=True)
    ref = score(d, d.tick_policy(np.full(len(d.s_in), 4)), PER)
    key = lambda g: res[str(g)]["M2_train"] + res[str(g)]["IMIT1_train"]
    best = sorted(grid, key=lambda g: -key(g))
    lines = []
    def L(s=""): lines.append(s); print(s)
    L(f"CROWDHOLD rules: {len(grid)} chosen on TRAIN (M2 + IMIT1 engine SOL/day, measured landing). TODAY c4: TRAIN M2 {ref['M2_train']:+.2f} IMIT1 {ref['IMIT1_train']:+.2f}"
      f" | first 11 h M2 {ref['M2_tr1']:+.2f} IMIT1 {ref['IMIT1_tr1']:+.2f} | VAL M2 {ref['M2_val']:+.2f} IMIT1 {ref['IMIT1_val']:+.2f}")
    L("rule = (crowd c, quiet sell tick kq, crowded min tick kmin, stall window m, buy threshold b, cap)")
    for g in best[:25]:
        r = res[str(g)]
        L(f"  {str(g):28s} TRAIN M2 {r['M2_train']:+6.2f} IMIT1 {r['IMIT1_train']:+6.2f} | first 11 h M2 {r['M2_tr1']:+6.2f} IMIT1 {r['IMIT1_tr1']:+6.2f} | VAL M2 {r['M2_val']:+6.2f} IMIT1 {r['IMIT1_val']:+6.2f}")
    # stability: rank on the first 11 h only, then see VAL
    best1 = sorted(grid, key=lambda g: -(res[str(g)]["M2_tr1"] + res[str(g)]["IMIT1_tr1"]))
    L("\nchosen on the first 11 h only (09:45-21:00) -> VAL (21:00-01:00):")
    for g in best1[:10]:
        r = res[str(g)]
        L(f"  {str(g):28s} first 11 h M2 {r['M2_tr1']:+6.2f} IMIT1 {r['IMIT1_tr1']:+6.2f} | VAL M2 {r['M2_val']:+6.2f} IMIT1 {r['IMIT1_val']:+6.2f}")
    json.dump(dict(res=res, ref=ref, best=[list(g) for g in best[:25]], best_tr1=[list(g) for g in best1[:10]]), open(f"{OUT}.json", "w"))
    open(f"{OUT}.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")

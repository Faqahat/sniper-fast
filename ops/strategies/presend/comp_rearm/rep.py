#!/usr/bin/env python3
"""tables from res_*.pkl (INFERRED). net per window = gross(0.696 SOL, TP20, SL50, cut) - trip cost per fill - 5,120 lamports per landed
failed try. delta = scenario - base, same draws. SOL/day = per usable hour x 24. 90% CI: resample hours (and draws)."""
import pickle, collections, sys, time, numpy as np
D = "/home/it/sniper-data/comp_rearm"
TRIP = float(sys.argv[1]) if len(sys.argv) > 1 else 2.9e-3
TRAIN = ("D2", "D3", "D4", "D5"); TEST = ("D6", "D7", "D7b")
LBL = {"D2": "10-24", "D3": "10-25", "D4": "10-26", "D5": "10-27", "D6": "10-28", "D7": "10-29 00-01h", "D7b": "10-29 r37 08-16h"}
R = {d: pickle.load(open(f"{D}/res_{d}.pkl", "rb")) for d in TRAIN + TEST}
SZ = int(0.696e9)


def hour(bt): return int(bt // 3600)
def pkth(h): return int(time.gmtime(h * 3600 + 18000).tm_hour)


def per_hour(rows, cut):
    """hour -> [net SOL, extra fills, base fills, extra nets list]"""
    H = collections.defaultdict(lambda: [0.0, 0, 0, []])
    for r in rows:
        if not r["armed"]: continue
        h = hour(r["bt"]); n = -r["nfail"] * 5120 / 1e9
        if r.get("filled"):
            g = r["grid"][(SZ, 0.20, cut)] / 1e9 - TRIP; n += g
            if r["kind"] == "re": H[h][1] += 1; H[h][3].append(g)
            else: H[h][2] += 1
        H[h][0] += n
    return H


def stats(days, scen, cut, filt=lambda h: True):
    hrs = []; dsum = []  # per (day, hour): delta per draw
    top = []; xf = []; bf = []
    for d in days:
        o = R[d]["out"]; hs = [h // 3600 for h in R[d]["meta"]["hours"]]
        hs = [h for h in hs if filt(pkth(h))]
        nd = len(o["base"])
        M = np.zeros((len(hs), nd)); XF = np.zeros(nd); BF = np.zeros(nd); T5 = np.zeros(nd)
        for k in range(nd):
            Hb = per_hour(o["base"][k]["rows"], cut); Hs = per_hour(o[scen][k]["rows"], cut)
            ex = []
            for i, h in enumerate(hs):
                M[i, k] = Hs[h][0] - Hb[h][0]; XF[k] += Hs[h][1]; BF[k] += Hs[h][2] - Hb[h][2]; ex += Hs[h][3]
            T5[k] = sum(sorted(ex, reverse=True)[:5])
        hrs.append(M); xf.append(XF.mean()); bf.append(BF.mean()); top.append(T5.mean())
    M = np.vstack(hrs) if hrs else np.zeros((0, 1))
    nh = len(M)
    if nh == 0: return None
    pt = M.mean() * 24
    rng = np.random.default_rng(7); bs = []
    for _ in range(2000):
        hi = rng.integers(nh, size=nh); di = rng.integers(M.shape[1], size=M.shape[1])
        bs.append(M[hi][:, di].mean() * 24)
    lo, hi_ = np.percentile(bs, [5, 95])
    w5 = (M.sum(0).mean() - sum(top)) / nh * 24
    return dict(pt=pt, lo=lo, hi=hi_, w5=w5, xf=sum(xf) / nh * 24, bf=sum(bf) / nh * 24, nh=nh)


def base_level(days, cut):
    v = []; n = 0
    for d in days:
        o = R[d]["out"]["base"]; hs = set(h // 3600 for h in R[d]["meta"]["hours"])
        v.append(np.mean([sum(x[0] for h, x in per_hour(o[k]["rows"], cut).items() if h in hs) for k in o])); n += len(hs)
    return sum(v) / n * 24


scens = [s for s in R["D2"]["out"] if s != "base"]
print(f"trip cost {TRIP*1e3:.1f} mSOL; failed try 5,120 lamports; size 0.696 SOL TP 20% SL 50%\n")
for cut in (0.0, 0.2):
    print(f"base level (SOL/day): TRAIN {base_level(TRAIN, cut):+.2f}  TEST {base_level(TEST, cut):+.2f}  (followers cut {cut:.0%})")
for nm, days in (("TRAIN (10-24..10-27)", TRAIN), ("TEST frozen (10-28 -> 10-29 16h)", TEST)):
    print(f"\n### {nm}: added SOL/day over base")
    print("| rule | extra windows/day | extra fills/day | base fills lost/day | delta all followers [90% CI] | delta -20% followers [90% CI] | -20% w/o top 5 extra fills |")
    print("|---|---|---|---|---|---|---|")
    for s in scens:
        a = stats(days, s, 0.0); b = stats(days, s, 0.2)
        nw = sum(R[d]["meta"]["n"][s] for d in days) / a["nh"] * 24
        print(f"| {s} | {nw:,.0f} | {a['xf']:.0f} | {-a['bf']:.0f} | {a['pt']:+.2f} [{a['lo']:+.2f}, {a['hi']:+.2f}] | {b['pt']:+.2f} [{b['lo']:+.2f}, {b['hi']:+.2f}] | {b['w5']:+.2f} |")
print("\n### TEST per day, -20% followers (SOL/day)")
print("| rule | " + " | ".join(LBL[d] for d in TEST) + " | TEST day 09-21 PKT | TEST night |")
print("|---|" + "---|" * (len(TEST) + 2))
for s in scens:
    cells = [f"{stats((d,), s, 0.2)['pt']:+.2f}" for d in TEST]
    dy = stats(TEST, s, 0.2, lambda h: 9 <= h < 21); ng = stats(TEST, s, 0.2, lambda h: not (9 <= h < 21))
    print(f"| {s} | " + " | ".join(cells) + f" | {dy['pt']:+.2f} | {ng['pt']:+.2f} |")
# per extra fill economics
print("\n### extra (competitor) windows: per-window economics, TEST, all followers")
print("| rule | windows armed | fill rate | mean net per fill mSOL | failed-try fee per armed window mSOL |")
print("|---|---|---|---|---|")
for s in scens:
    na = nf = 0; g = []; fee = 0.0
    for d in TEST:
        for k, x in R[d]["out"][s].items():
            for r in x["rows"]:
                if r["kind"] != "re" or not r["armed"]: continue
                na += 1; fee += r["nfail"] * 5120 / 1e6
                if r.get("filled"): nf += 1; g.append(r["grid"][(SZ, 0.20, 0.0)] / 1e6 - TRIP * 1e3)
    print(f"| {s} | {na/10:,.0f} | {nf/max(na,1):.1%} | {np.mean(g) if g else float('nan'):+.1f} | {fee/max(na,1):.2f} |")

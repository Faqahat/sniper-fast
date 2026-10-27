#!/usr/bin/env python3
"""DENSITY step 3 (read-only): calibration (stream 'cal' vs live, MEASURED live) and the lever tables (INFERRED).
Net per window = P&L of the fill (incl. its path's tip) - failed-try fees - the token-account close fee (5,020 lamports, as calib28).
Ranges: bootstrap over windows (10,000 resamples, stratified by run) of the per-window mean difference vs 'base' (paired:
common random numbers), so the range is the window sample's, not the model's.
usage: d3_tables.py [--tag main] [--runs 24,25,26,27,28]"""
import sys, os, pickle, json, argparse, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib

RENT = 5020
ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="main"); ap.add_argument("--runs", default="24,25,26,27,28")
A = ap.parse_args()
RUNS = [int(r) for r in A.runs.split(",")]
rng = np.random.default_rng(7)
NB = 10000

Z = {}
for r in RUNS:
    fn = f"{dlib.DATA}/rep_r{r}_{A.tag}.pkl"
    if os.path.exists(fn): Z[r] = pickle.load(open(fn, "rb"))
    for ext in ("extra", "extra2"):                     # scenarios added after a run's main pass (same seeds, same windows)
        fx = f"{dlib.DATA}/rep_r{r}_{ext}.pkl"
        if r in Z and os.path.exists(fx):
            X = pickle.load(open(fx, "rb"))
            for k, v in X["out"].items(): Z[r]["out"].setdefault(k, v)
RUNS = [r for r in RUNS if r in Z]


def arrs(r, scen):
    """-> dict of [draws, windows] arrays for a scenario (windows in the meta's live order)"""
    M = Z[r]["meta"]; ws = [x["w"] for x in M["live"]]
    dr = Z[r]["out"][scen]
    f = np.array([[by[w][1] for w in ws] for _, by in dr], float)
    pnl = np.array([[by[w][2] - (RENT if by[w][1] else 0) for w in ws] for _, by in dr], float) / 1e9
    fee = np.array([[by[w][3] for w in ws] for _, by in dr], float) / 1e9
    sent = np.array([[by[w][4] for w in ws] for _, by in dr], float)
    rs = np.array([[by[w][5] for w in ws] for _, by in dr], float)
    path = [[by[w][6] for w in ws] for _, by in dr]
    return dict(f=f, pnl=pnl, fee=fee, net=pnl - fee, win=(f > 0) & (pnl > 0), sent=sent, rs=rs, path=path)


def live(r):
    M = Z[r]["meta"]
    L = [x["live"] for x in M["live"]]
    return dict(f=np.array([x["filled"] for x in L], float), pnlrb=np.array([(x["pnl"] + x["rb"]) for x in L], float) / 1e9,
                fee=np.array([x["fee"] for x in L], float) / 1e9, net=np.array([x["net"] for x in L], float) / 1e9,
                dumped=np.array([x["dumped"] for x in M["live"]], bool), n_att=sum(x["n_att"] for x in L))


def p5(a): return float(np.percentile(a, 5))
def p95(a): return float(np.percentile(a, 95))


# ------------------------------------------------------------------------------------------------- 1. calibration
print("## Calibration: live (MEASURED) vs replay at live settings (cal stream; INFERRED), 100 draws\n")
print("| Run | Size | Hours | Windows | Dump windows | Fills live / replay | Share of dump windows filled, live / replay | Wins live / replay | Fees live / replay | **Net live / replay [5-95%]** | Live pct | f_win | f_loss | Fill agreement |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
CAL = {}
tot = collections.defaultdict(float); totd = collections.defaultdict(lambda: 0)
pooled_rw = []; pooled_rl = []
for r in RUNS:
    M = Z[r]["meta"]; lv = live(r); c = arrs(r, "cal")
    nd = lv["dumped"].sum()
    lw = lv["pnlrb"][(lv["f"] > 0) & (lv["pnlrb"] > 0)].sum(); ll = lv["pnlrb"][(lv["f"] > 0) & (lv["pnlrb"] <= 0)].sum()
    rw = np.where(c["win"], c["pnl"], 0).sum(1).mean(); rl = np.where((c["f"] > 0) & ~c["win"], c["pnl"], 0).sum(1).mean()
    fw = lw / rw if rw else np.nan; fl = ll / rl if rl else np.nan
    netd = c["net"].sum(1)
    pctl = (netd <= lv["net"].sum()).mean() * 100
    pf = c["f"].mean(0)
    agree = np.mean(np.where(lv["f"] > 0, pf, 1 - pf))
    CAL[r] = dict(fw=fw, fl=fl, live_net=float(lv["net"].sum()), rep_net=float(netd.mean()), pct=pctl, lw=lw, ll=ll, rw=rw, rl=rl,
                  live_fills=int(lv["f"].sum()), rep_fills=float(c["f"].sum(1).mean()), dumped=int(nd))
    nlw = int(((lv["f"] > 0) & (lv["pnlrb"] > 0)).sum()); rwn = c["win"].sum(1).mean()
    print(f"| r{r} | {M['size'] / 1e9:.2f} | {M['hours']:.1f} | {len(M['live'])} | {nd} | {int(lv['f'].sum())} / {c['f'].sum(1).mean():.1f} | "
          f"{lv['f'].sum() / nd * 100:.0f}% / {c['f'].sum(1).mean() / nd * 100:.0f}% | {nlw} / {rwn:.1f} | {lv['fee'].sum():.3f} / {c['fee'].sum(1).mean():.3f} | "
          f"**{lv['net'].sum():+.3f} / {netd.mean():+.3f} [{p5(netd):+.3f}, {p95(netd):+.3f}]** | {pctl:.0f}th | {fw:.2f} | {fl:.2f} | {agree * 100:.0f}% |")
    for k, v in (("lw", lw), ("ll", ll), ("rw", rw), ("rl", rl), ("ln", lv["net"].sum()), ("rn", netd.mean()), ("lf", lv["f"].sum()), ("rf", c["f"].sum(1).mean()),
                 ("nd", nd), ("lfee", lv["fee"].sum()), ("rfee", c["fee"].sum(1).mean()), ("h", M["hours"]), ("nlw", nlw), ("rwn", rwn)):
        tot[k] += v
FW = tot["lw"] / tot["rw"]; FL = tot["ll"] / tot["rl"]
print(f"| **All** | | {tot['h']:.1f} | | {tot['nd']:.0f} | {tot['lf']:.0f} / {tot['rf']:.1f} | {tot['lf'] / tot['nd'] * 100:.0f}% / {tot['rf'] / tot['nd'] * 100:.0f}% | "
      f"{tot['nlw']:.0f} / {tot['rwn']:.1f} | {tot['lfee']:.3f} / {tot['rfee']:.3f} | **{tot['ln']:+.3f} / {tot['rn']:+.3f}** | | **{FW:.2f}** | **{FL:.2f}** | |")
print(f"\nPooled calibration factor (INFERRED): winning fills x {FW:.2f}, losing fills x {FL:.2f}.")
calnet = sum(CAL[r]["fw"] * CAL[r]["rw"] + CAL[r]["fl"] * CAL[r]["rl"] for r in RUNS)

# ------------------------------------------------------------------------------------------------- 2. levers
SC = [s for s in Z[RUNS[0]]["out"] if s != "cal" and all(s in Z[r]["out"] for r in RUNS)]
BASE = {}
for r in RUNS: BASE[r] = arrs(r, "base")


def cal_net(a):
    """calibrated: winning fills x FW, losing fills x FL (pooled factors)"""
    return np.where(a["win"], a["pnl"] * FW, np.where(a["f"] > 0, a["pnl"] * FL, 0.0)) - a["fee"]


def boot(deltas):
    """deltas: {run: per-window mean deltas} -> bootstrap totals (stratified by run)"""
    out = np.zeros(NB)
    for r, d in deltas.items():
        n = len(d)
        idx = rng.integers(0, n, size=(NB, n))
        out += d[idx].sum(1)
    return out


from dsim import TIPS
BASEC = {}; BASEL = {}
for r in RUNS:
    if "base_cut" in Z[r]["out"]: BASEC[r] = arrs(r, "base_cut")
    if "base_lag15" in Z[r]["out"]: BASEL[r] = arrs(r, "base_lag15")
RES = {}
for s in SC:
    row = dict(per={}, tot={})
    dl = {}; dlc = {}
    tf = tw = tn = tfee = ttip = tsent = trs = 0.0; tdn = 0.0; tcn = 0.0; bnet = 0.0
    for r in RUNS:
        if s not in Z[r]["out"]: continue
        a = arrs(r, s); b = BASEC[r] if s.endswith("_cut") else BASEL[r] if s.endswith("_lag15") else BASE[r]
        d = (a["net"] - b["net"]).mean(0); dl[r] = d
        dc = (cal_net(a) - cal_net(b)).mean(0); dlc[r] = dc
        tips = sum(TIPS.get(p.split("#")[0], 1_000_000) - 200_000 for drow in a["path"] for p in drow if p) / len(a["path"]) / 1e9
        ttip += tips
        bt = boot({r: d})
        nd = sum(x["dumped"] for x in Z[r]["meta"]["live"])
        row["per"][r] = dict(fills=a["f"].sum(1).mean(), share=a["f"].sum(1).mean() / nd, wins=a["win"].sum(1).mean(), net=a["net"].sum(1).mean(),
                             fee=a["fee"].sum(1).mean(), d=d.sum(), lo=p5(bt), hi=p95(bt), dc=dc.sum(), sent=a["sent"].sum(1).mean(), rs=a["rs"].sum(1).mean(),
                             h=Z[r]["meta"]["hours"], pos=(bt > 0).mean(), tips=tips)
        tf += a["f"].sum(1).mean(); tw += a["win"].sum(1).mean(); tn += a["net"].sum(1).mean(); tfee += a["fee"].sum(1).mean(); tdn += nd
        tsent += a["sent"].sum(1).mean(); trs += a["rs"].sum(1).mean(); tcn += cal_net(a).sum(1).mean()
    bt = boot(dl); btc = boot(dlc)
    H = sum(Z[r]["meta"]["hours"] for r in dl)
    row["tot"] = dict(fills=tf, share=tf / tdn if tdn else 0, wins=tw, net=tn, fee=tfee, d=sum(v.sum() for v in dl.values()), lo=p5(bt), hi=p95(bt),
                      dc=sum(v.sum() for v in dlc.values()), lo_c=p5(btc), hi_c=p95(btc), h=H, pos=(bt > 0).mean(), sent=tsent, rs=trs, cnet=tcn, tips=ttip)
    RES[s] = row

json.dump(dict(CAL=CAL, FW=FW, FL=FL, RES=RES), open(f"{dlib.DATA}/tables_{A.tag}.json", "w"), default=float)


def fmt_row(s):
    t = RES[s]["tot"]
    cells = []
    for r in RUNS:
        p = RES[s]["per"].get(r)
        cells.append(f"{p['d']:+.2f}" if p else "")
    return (f"| {s} | " + " | ".join(cells) + f" | **{t['d']:+.2f}** [{t['lo']:+.2f}, {t['hi']:+.2f}] | {t['pos'] * 100:.0f}% | {t['dc']:+.2f} [{t['lo_c']:+.2f}, {t['hi_c']:+.2f}] | "
            f"{t['d'] / t['h']:+.3f} | {t['fills']:.0f} | {t['share'] * 100:.0f}% | {t['wins']:.0f} | {t['net']:+.2f} | {t['fee']:.3f} | {t['tips']:.3f} | {t['sent'] / 1000:.0f}k / {t['rs'] / 1000:.0f}k |")


print("\n## Levers (INFERRED; change vs base = live settings, same windows; SOL)\n")
print("| Scenario | " + " | ".join(f"r{r}" for r in RUNS) + " | **Total change** [5-95%] | Boot > 0 | Calibrated change [5-95%] | Per hour | Fills | Dump windows filled | Wins | Net (abs) | Failed-try fees | Extra tips | Tries sent / refused |")
print("|---|" + "---|" * len(RUNS) + "---|---|---|---|---|---|---|---|---|---|---|")
for s in SC: print(fmt_row(s))
print()
for s in ("base", "base_cut"):
    if s in RES:
        t = RES[s]["tot"]
        print(f"{s}: fills {t['fills']:.0f}, net {t['net']:+.3f} (calibrated {t['cnet']:+.3f}), fees {t['fee']:.3f} over {t['h']:.1f} h")

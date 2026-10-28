#!/usr/bin/env python3
"""REARM step 2b (read-only): the validation table from val_<run>.pkl (r2_validate.py). Per run: live (MEASURED) vs replay (INFERRED,
mean of the draws, 5-95%): fills, share of 'dump windows' (the tape fell >= 12% inside the window) filled, wins, failed-try fees, net
(= fill P&L incl. rent back - the 5,020-lamport ATA close fee - failed-try fees), where live sits in the draws, window-level fill
agreement, and the live/replay ratio. Out: val.txt"""
import pickle, os, sys, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
RENT = 5020
runs = sys.argv[1].split(",") if len(sys.argv) > 1 else ["a24", "a25", "a26", "a27", "a28", "a29", "a30", "a31", "a32", "a33", "f26"]
L = []
def P(s=""): print(s); L.append(s)
P("# Validation: live pre-send (MEASURED) vs the replay at live settings ('cal' stream: live windows forced armed; INFERRED), dv8 tape cuts")
P("| Run | Size, k, cap | Windows | Dump windows | Fills live / replay | Dump windows filled live / replay | Wins live / replay | Failed-try fees live / replay | **Net live / replay [5-95%]** | Live pctile | Fill agreement |")
P("|---|---|---|---|---|---|---|---|---|---|---|")
T = collections.defaultdict(float); per = {}
for r in runs:
    fn = f"{OUT}/val_{r}.pkl"
    if not os.path.exists(fn): continue
    Z = pickle.load(open(fn, "rb")); M = Z["meta"]; ws = [x["w"] for x in M["live"]]
    lv = [x["live"] for x in M["live"]]
    lf = np.array([x["filled"] for x in lv], float); lnet = np.array([x["net"] for x in lv], float) / 1e9
    lpnl = np.array([x["pnl"] + x["rb"] for x in lv], float) / 1e9; lfee = np.array([x["fee"] for x in lv], float) / 1e9
    dumped = np.array([x["dumped"] for x in M["live"]], bool)
    f = np.array([[by[w][1] for w in ws] for _, by in Z["out"]], float)
    pnl = np.array([[by[w][2] - (RENT if by[w][1] else 0) for w in ws] for _, by in Z["out"]], float) / 1e9
    fee = np.array([[by[w][3] for w in ws] for _, by in Z["out"]], float) / 1e9
    net = (pnl - fee).sum(1)
    pf = f.mean(0); agree = np.mean(np.where(lf > 0, pf, 1 - pf))
    lw = int(((lf > 0) & (lpnl > 0)).sum()); rw = ((f > 0) & (pnl > 0)).sum(1).mean()
    pct = (net <= lnet.sum()).mean() * 100
    P(f"| {r} | {M['size'] / 1e9:.2f}, k{M['k']}, {M['rate']}/s | {len(ws)} | {dumped.sum()} | {int(lf.sum())} / {f.sum(1).mean():.1f} | {lf[dumped].sum() / max(dumped.sum(), 1) * 100:.0f}% / {f[:, dumped].sum(1).mean() / max(dumped.sum(), 1) * 100:.0f}% | "
      f"{lw} / {rw:.1f} | {lfee.sum():.3f} / {fee.sum(1).mean():.3f} | **{lnet.sum():+.3f} / {net.mean():+.3f} [{np.percentile(net, 5):+.3f}, {np.percentile(net, 95):+.3f}]** | {pct:.0f} | {agree * 100:.0f}% |")
    per[r] = dict(live=lnet.sum(), rep=net.mean(), lf=lf.sum(), rf=f.sum(1).mean(), live_pf=lpnl[lf > 0].sum(), rep_pf=np.where(f > 0, pnl, 0).sum(1).mean(),
                  lfee=lfee.sum(), rfee=fee.sum(1).mean(), nd=dumped.sum(), lfd=lf[dumped].sum(), rfd=f[:, dumped].sum(1).mean(), draws=net)
    for k, v in per[r].items():
        if k != "draws": T[k] += v
P(f"| **All** | | | {T['nd']:.0f} | {T['lf']:.0f} / {T['rf']:.1f} | {T['lfd'] / T['nd'] * 100:.0f}% / {T['rfd'] / T['nd'] * 100:.0f}% | | {T['lfee']:.3f} / {T['rfee']:.3f} | **{T['live']:+.3f} / {T['rep']:+.3f}** | | |")
P("")
P(f"Pooled live / replay: net {T['live'] / T['rep']:.2f}; fill P&L (before failed-try fees) {T['live_pf'] / T['rep_pf']:.2f}; fills {T['lf'] / T['rf']:.2f}; failed-try fees {T['lfee'] / T['rfee']:.2f}")
# bootstrap the pooled ratio over runs (run-level resampling) and per-fill gap
rs = [r for r in per]
rng = np.random.default_rng(3); bs = []
for _ in range(5000):
    pick = rng.choice(rs, len(rs))
    lv_ = sum(per[x]["live"] for x in pick); rp_ = sum(per[x]["rep"] for x in pick)
    bs.append(lv_ / rp_ if rp_ > 0 else np.nan)
bs = np.array(bs); bs = bs[np.isfinite(bs)]
P(f"Run-bootstrap of live/replay net ratio: 5-95% [{np.percentile(bs, 5):.2f}, {np.percentile(bs, 95):.2f}] (median {np.median(bs):.2f})")
P(f"Per fill: live {T['live_pf'] / T['lf'] * 1000:+.2f} mSOL vs replay {T['rep_pf'] / T['rf'] * 1000:+.2f} (gap {(T['live_pf'] / T['lf'] - T['rep_pf'] / T['rf']) * 1000:+.2f} mSOL/fill)")
bg = []; br = []
for _ in range(5000):
    pick = rng.choice(rs, len(rs))
    lf_ = sum(per[x]["lf"] for x in pick); rf_ = sum(per[x]["rf"] for x in pick)
    bg.append((sum(per[x]["live_pf"] for x in pick) / lf_ - sum(per[x]["rep_pf"] for x in pick) / rf_) * 1000)
    br.append(sum(per[x]["live_pf"] for x in pick) / sum(per[x]["rep_pf"] for x in pick))
P(f"Run-bootstrap of the per-fill gap (live - replay, mSOL/fill): 5-95% [{np.percentile(bg, 5):+.2f}, {np.percentile(bg, 95):+.2f}]; fill-P&L ratio 5-95% [{np.percentile(br, 5):.2f}, {np.percentile(br, 95):.2f}]")
P("Runs where live is below the replay's 5th pct: " + ", ".join(r for r in rs if per[r]["live"] < np.percentile(per[r]["draws"], 5)))
P("Runs where live is above the replay's 95th pct: " + ", ".join(r for r in rs if per[r]["live"] > np.percentile(per[r]["draws"], 95)))
open(f"{OUT}/val.txt", "w").write("\n".join(L) + "\n")

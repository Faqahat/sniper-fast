#!/usr/bin/env python3
"""LIVE27 step 3: calibration of the replay on run 27's own 177 live windows (stream 'cal': forced arm, live QUIET stops kept).
Live = MEASURED (realized + rent back - failed-try fees, engine-logged as eval_live.py; chain-found fees also shown).
Replay = INFERRED; a fill's P&L gets the token-account close fee (-5,020 lamports, MEASURED: rent 1,513,840 paid, 1,508,820 back) so
it is booked as live books it.
usage: calib27.py POOL [TAG]"""
import sys, os, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib27 as L

RENT = 5020


def pct(a, q): return float(np.percentile(a, q))


def load(pool, tag="main"):
    return pickle.load(open(f"{L.DATA}/replay27_{pool}_{tag}.pkl", "rb"))


def wnet(r): return r["net"] - (RENT if r["filled"] else 0)


def wpnl(r): return r["pnl"] - (RENT if r["filled"] else 0)


def summary(Z, stream, keys):
    """per draw totals over the given window keys"""
    dr = Z["out"][stream]
    f = np.array([sum(by[k]["filled"] for k in keys if k in by) for _, by in dr])
    wn = np.array([sum(1 for k in keys if k in by and by[k]["filled"] and wpnl(by[k]) > 0) for _, by in dr])
    p = np.array([sum(wpnl(by[k]) for k in keys if k in by and by[k]["filled"]) for _, by in dr]) / 1e9
    fe = np.array([sum(by[k]["fees"] for k in keys if k in by) for _, by in dr]) / 1e9
    n = np.array([sum(wnet(by[k]) for k in keys if k in by) for _, by in dr]) / 1e9
    return dict(fills=f, wins=wn, pnl=p, fees=fe, net=n)


def live_tot(Z, keys):
    lv = {x["key"]: x["live"] for x in Z["meta"]["live"]}
    X = [lv[k] for k in keys]
    return dict(fills=sum(x["filled"] for x in X), wins=sum(1 for x in X if x["filled"] and x["pnl"] + x["rb"] > 0),
                pnl=sum(x["pnl"] + x["rb"] for x in X if x["filled"]) / 1e9, fees=sum(x["fee"] for x in X) / 1e9,
                fees_chain=sum(x["fee_chain"] for x in X) / 1e9, net=sum(x["net"] for x in X) / 1e9)


def line(name, Lv, Sm):
    def f(k, fmt="%+.4f"):
        a = Sm[k]; return (fmt % a.mean()) + " [" + (fmt % pct(a, 5)) + ", " + (fmt % pct(a, 95)) + "]"
    pn = (Sm["net"] <= Lv["net"]).mean() * 100
    return (f"| {name} | {Lv['fills']} / {f('fills', '%.1f')} | {Lv['wins']} / {Sm['wins'].mean():.1f} | {Lv['pnl']:+.4f} / {f('pnl')} | "
            f"{Lv['fees']:.4f} ({Lv['fees_chain']:.4f}) / {Sm['fees'].mean():.4f} | **{Lv['net']:+.4f}** / **{f('net')}** | {pn:.0f}th |")


def per_window(Z, stream, keys):
    dr = Z["out"][stream]
    pf = {k: np.mean([by[k]["filled"] for _, by in dr]) for k in keys}
    mn = {k: np.mean([wnet(by[k]) for _, by in dr]) / 1e9 for k in keys}
    cp = {}
    for k in keys:
        v = [wpnl(by[k]) for _, by in dr if by[k]["filled"]]
        cp[k] = (np.mean(v) / 1e9 if v else None, len(v) / len(dr))
    return pf, mn, cp


if __name__ == "__main__":
    pool = sys.argv[1]; tag = sys.argv[2] if len(sys.argv) > 2 else "main"
    Z = load(pool, tag)
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}
    allk = [x["key"] for x in M["live"]]
    groups = [("All 177 windows", allk),
              ("Warm-up (74)", [k for k in allk if lv[k]["phase"] == "warm"]),
              ("  of which would-skip, all 4 signals (20)", [k for k in allk if lv[k]["phase"] == "warm" and lv[k]["all4"]]),
              ("  of which kept (54)", [k for k in allk if lv[k]["phase"] == "warm" and not lv[k]["all4"]]),
              ("Rule on (103)", [k for k in allk if lv[k]["phase"] == "on"]),
              ("Stopped by QUIET (45)", [k for k in allk if lv[k]["d_stop"] is not None]),
              ("Not stopped (132)", [k for k in allk if lv[k]["d_stop"] is None]),
              ("All without w120 (+0.220 TP)", [k for k in allk if k != ("L", 120)])]
    print(f"pool {pool}, {M['draws']} draws, slot_ms {M['slot_ms']:.1f}, cut {M['cut']} lag {M['lag']}")
    print("| Group | Fills live / replay | Wins | Realized+rent live / replay | Fees live (chain) / replay | Net live / replay | Live pct |")
    print("|---|---|---|---|---|---|---|")
    for name, ks in groups:
        print(line(name, live_tot(Z, ks), summary(Z, "cal", ks)))
    pf, mn, cp = per_window(Z, "cal", allk)
    agree = np.mean([pf[k] if lv[k]["live"]["filled"] else 1 - pf[k] for k in allk])
    brier = np.mean([(pf[k] - lv[k]["live"]["filled"]) ** 2 for k in allk])
    print(f"fill/no-fill agreement {agree * 100:.1f}%  Brier {brier:.3f}  (base rate {np.mean([lv[k]['live']['filled'] for k in allk]):.2f})")
    # fills: live P&L vs the replay's P&L given a fill, on the live-filled windows
    fk = [k for k in allk if lv[k]["live"]["filled"]]
    a = np.array([(lv[k]["live"]["pnl"] + lv[k]["live"]["rb"]) / 1e9 for k in fk]); b = np.array([cp[k][0] if cp[k][0] is not None else np.nan for k in fk])
    ok = ~np.isnan(b)
    print(f"live-filled windows {len(fk)}: replay fills them {np.mean([pf[k] for k in fk]) * 100:.0f}% of draws; P&L per fill live {a.mean():+.4f} vs replay-given-fill "
          f"{np.nanmean(b):+.4f} (corr {np.corrcoef(a[ok], b[ok])[0, 1]:.2f}; same sign {np.mean(np.sign(a[ok]) == np.sign(b[ok])) * 100:.0f}%)")
    nk = [k for k in allk if not lv[k]["live"]["filled"]]
    print(f"live-unfilled windows {len(nk)}: replay fills them {np.mean([pf[k] for k in nk]) * 100:.0f}% of draws; replay P&L of those fills per window "
          f"{np.mean([mn[k] for k in nk]):+.4f}")
    # the biggest per-window differences
    diff = sorted(allk, key=lambda k: -abs(lv[k]["live"]["net"] / 1e9 - mn[k]))[:12]
    for k in diff:
        x = lv[k]
        print(f"  w{x['w']:3d} {L.hm(x['t_ns'])} {x['mint'][:8]} live {x['live']['net'] / 1e9:+.4f} ({x['live']['why']}, {x['live']['exit']}) replay mean {mn[k]:+.4f} "
              f"fill p {pf[k]:.2f} pnl|fill {cp[k][0] if cp[k][0] is not None else float('nan'):+.4f}")

#!/usr/bin/env python3
"""LAST_HOUR tables (read-only): lh/lasthour_<tag>.pkl -> per 15 min / per hour replay rows, the run-22 check (replay vs live vs
the engine's paper shadow), window-level fill agreement. usage: lhreport.py [tag]"""
import sys, os, pickle, collections, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib

LH = "/home/moiz/sniper-data/presend_real/lh"
tag = sys.argv[1] if len(sys.argv) > 1 else "main"
P = pickle.load(open(f"{LH}/lasthour_{tag}.pkl", "rb"))
R = P["R"]; bins = P["bins"]; LV = P["live"]
f = lambda t: rlib.pkt(t, "%H:%M")
fs = lambda t: rlib.pkt(t, "%H:%M:%S")

def band(x):
    x = np.asarray(x, float)
    return np.mean(x), np.percentile(x, 5), np.percentile(x, 95)

def agg(stream, a, b):
    """per draw: fills, wins (fill P&L > 0), realized, failed-try fees, net over windows whose trigger time is in [a, b)"""
    out = []
    for seed, rows in R[stream]:
        x = [r for r in rows if a <= r[0] < b]
        out.append((sum(r[1] for r in x), sum(1 for r in x if r[1] and r[3] > 0), sum(r[3] for r in x) / 1e9, sum(r[4] for r in x) / 1e9,
                    sum(r[2] for r in x) / 1e9, len(x)))
    return np.array(out)

def usable_min(a, b):
    return sum((min(x["t1"], b) - max(x["t0"], a)) for x in bins if x["use"] and x["t1"] > a and x["t0"] < b) / 60.0

def row(stream, a, b, label=None):
    A = agg(stream, a, b)
    n, lo, hi = band(A[:, 4])
    pos = (A[:, 4] > 0).mean() * 100
    return (f"| {label or (f(a) + '-' + f(b))} | {usable_min(a, b):.0f} | {np.mean(A[:, 5]):.0f} | {np.mean(A[:, 0]):.1f} | {np.mean(A[:, 1]):.1f} | "
            f"{np.mean(A[:, 2]):+.3f} | {np.mean(A[:, 3]):.3f} | **{n:+.3f}** | {lo:+.3f} to {hi:+.3f} | {pos:.0f}% |"), A

H = "| PKT | usable min | windows armed | fills | wins | realized SOL | failed-try fees | net SOL | 90% band | draws > 0 |\n|---|---|---|---|---|---|---|---|---|---|"
ts, te = P["start"], P["end"]
t02 = rlib.pk("10-26 02:00")
print(f"replay window {rlib.pkt(ts)} -> {rlib.pkt(te)} PKT; draws {len(R['main'])}; armable main {P['n_main']}")
print("\n## per 15 min, 02:00 ->", f(te))
print(H)
cuts = list(range(t02, te, 900)) + [te]
for a, b in zip(cuts[:-1], cuts[1:]):
    print(row("main", a, b)[0])
print(row("main", t02, te, f"**02:00-{f(te)} total**")[0])
print(row("main", te - 3600, te, f"last 60 min {f(te - 3600)}-{f(te)}")[0])
print(row("main", rlib.pk("10-26 03:00"), te, f"03:00-{f(te)}")[0])
print(row("main", t02, rlib.pk("10-26 03:00"), "02:00-03:00")[0])
print("\n## per hour, 22:00 -> 02:00 (night trend)")
print(H)
for h in ("10-25 22:00", "10-25 23:00", "10-26 00:00", "10-26 01:00"):
    a = rlib.pk(h); print(row("main", a, a + 3600)[0])
print(row("main", ts, t02, "22:00-02:00 total")[0])
print(row("main", ts, te, f"**22:00-{f(te)} all**")[0])

# ---- run 22 check -----------------------------------------------------------------------------------------------------------
v0, v1 = P["val_span"]
print(f"\n## run 22 check: span {fs(v0)} -> {fs(v1)} PKT")
W = LV["W"]
fills = [w for w in W if w["nfill"]]
dbl = [w for w in W if w["nfill"] > 1]
single = [w for w in fills if w["nfill"] == 1]
real_all = sum(w["pnl"] or 0 for w in fills)
real_single = sum(w["pnl"] or 0 for w in single)
print(f"live: windows armed {len(W)}, skips {dict(LV['skips'])}, tries sent {LV['n_att']}, landed records {LV['n_land']} res {dict(LV['res'])}")
print(f"live: fill windows {len(fills)} (fill txs {sum(w['nfill'] for w in fills)}), wins {sum(1 for w in fills if (w['pnl'] or 0) > 0)}; "
      f"realized (presend_live_realized sum) {real_all:+.4f}; failed-try fees {LV['fail_fee']:.4f} ({LV['fail_n']} landed failed tries); "
      f"engine fee counter {LV['stop']['fees'] / 1e9 if LV['stop'] else float('nan'):.4f}")
print(f"live excl. double-fill windows: {len(single)} fills, wins {sum(1 for w in single if (w['pnl'] or 0) > 0)}, realized {real_single:+.4f}, "
      f"net after ALL failed-try fees {real_single - LV['fail_fee']:+.4f}")
for w in dbl:
    print(f"  double fill w{w['w']} {w['mint'][:8]} at {fs(w['t'])}: fills {w['nfill']}, realized record {w['pnl']:+.4f} (counts one buy), "
          f"curve P&L both buys {w['curve_pnl']:+.4f} on {w['sol_in_curve']:.3f} SOL in, exit {w['exit']}")
print("live per-window:", [(fs(w["t"]), w["mint"][:6], w["nfill"], round(w["pnl"], 4) if w["pnl"] is not None else None) for w in fills])
for nm, a, b in (("A", v0, rlib.pk("10-26 02:30")), ("B", rlib.pk("10-26 02:30"), v1 + 60), ("all", v0, v1 + 60)):
    lw = [w for w in fills if a <= w["t"] < b]
    print(f" live {nm} {fs(a)}-{fs(b)}: fills {len(lw)} realized {sum(w['pnl'] or 0 for w in lw):+.4f} (excl. double {sum(w['pnl'] or 0 for w in lw if w['nfill'] == 1):+.4f})")
# shadow
print("\nshadow (paper, x 0.40/0.55; MEASURED records) by s_in time:")
for nm, a, b in (("A", rlib.pk("10-26 02:00"), rlib.pk("10-26 02:30")), ("B", rlib.pk("10-26 02:30"), rlib.pk("10-26 02:50"))):
    for rw in ("a", "b", "c"):
        x = [s for s in LV["shadow"] if s["row"] == rw and s["bt"] is not None and a <= s["bt"] < b]
        xn = [s for s in x if s["age"] != 0]
        print(f"  {nm} {f(a)}-{f(b)} row {rw}: fills {len(x)} net {sum(s['net'] for s in x):+.3f} | excl. create-slot: fills {len(xn)} net {sum(s['net'] for s in xn):+.3f}")
# replay on the same span
print("\nreplay, run-22 span:")
print(H)
for st, lab in (("val", "own stream (tokens created after 02:18:38)"), ("main", "continuous stream (full history)")):
    for a, b, nm in ((v0, rlib.pk("10-26 02:30"), "A"), (rlib.pk("10-26 02:30"), v1 + 1, "B"), (v0, v1 + 1, "all")):
        print(row(st, a, b, f"{lab} {nm} {fs(a)}-{fs(b)}")[0])
A = agg("val", v0, v1 + 1)
live_net_single = real_single - LV["fail_fee"]
for nm, val in (("live realized excl. double", real_single), ):
    pass
pct = lambda arr, v: (np.asarray(arr) < v).mean() * 100
print(f"live (excl. double) realized {real_single:+.4f} at the replay's {pct(A[:, 2], real_single):.0f}th pct of realized; "
      f"net {live_net_single:+.4f} at {pct(A[:, 4], live_net_single):.0f}th pct of net; fills {len(single)} at {pct(A[:, 0], len(single)):.0f}th pct of fills; "
      f"fees live {LV['fail_fee']:.4f} vs replay {np.mean(A[:, 3]):.4f}")
# window-level agreement (live armed windows vs replay val windows by trigger)
key_live = {(w["mint"], w["slot"]): w for w in W}
rep = collections.defaultdict(lambda: [0, 0, 0.0])
for seed, rows in R["val"]:
    for r in rows:
        k = (r[6], r[7]); rep[k][0] += 1; rep[k][1] += r[1]; rep[k][2] += r[2] / 1e9
nd = len(R["val"])
both = [k for k in key_live if k in rep]
print(f"\nwindows: live armed {len(key_live)}, replay armed (any draw) {len(rep)}, both {len(both)}; live-only {len(set(key_live) - set(rep))}, replay-only {len(set(rep) - set(key_live))}")
agree = []
for k in both:
    lf = 1 if key_live[k]["nfill"] else 0
    pf = rep[k][1] / max(rep[k][0], 1)
    agree.append(lf * pf + (1 - lf) * (1 - pf))
print(f"fill / no-fill agreement on shared windows: {np.mean(agree) * 100:.1f}% (live fills {sum(1 for k in both if key_live[k]['nfill'])}, replay mean fills on them "
      f"{sum(rep[k][1] / nd for k in both):.1f})")
lo = sorted(set(key_live) - set(rep))
print("live-only windows:", [(fs(key_live[k]["t"]), k[0][:6], key_live[k]["nfill"], key_live[k]["age"]) for k in lo])
ro = sorted(set(rep) - set(key_live))
print("replay-only windows (mean fills/draw):", [(k[0][:6], round(rep[k][1] / nd, 2)) for k in ro])
# per window side by side for live-filled windows
print("live-filled windows: live realized vs replay mean net when filled")
for k in both:
    w = key_live[k]
    if not w["nfill"]: continue
    print(f"  {fs(w['t'])} {k[0][:8]} live {w['pnl']:+.4f} (fills {w['nfill']}) | replay fill rate {rep[k][1] / nd:.2f}, mean net/draw {rep[k][2] / nd:+.4f}")

# ---- concentration: which windows carry the recent result ------------------------------------------------------------------
print("\n## concentration (main stream): mean net per armed window over the draws")
for a, b, nm in ((t02, te, "02:00-" + f(te)), (te - 3600, te, "last 60 min")):
    per = collections.defaultdict(float); fl = collections.defaultdict(float); when = {}
    for seed, rows in R["main"]:
        for r in rows:
            if a <= r[0] < b:
                k = (r[6], r[7]); per[k] += r[2] / 1e9 / len(R["main"]); fl[k] += r[1] / len(R["main"]); when[k] = r[0]
    top = sorted(per.items(), key=lambda x: -x[1])
    tot = sum(per.values())
    print(f"{nm}: total {tot:+.3f}; windows {len(per)}; without top 1 {tot - top[0][1]:+.3f}, top 2 {tot - top[0][1] - top[1][1]:+.3f}, "
          f"top 3 {tot - sum(x[1] for x in top[:3]):+.3f}; positive windows {sum(1 for v in per.values() if v > 0)}, negative {sum(1 for v in per.values() if v < 0)}")
    print("  top:", [(f(when[k]), k[0][:6], round(v, 3), round(fl[k], 2)) for k, v in top[:5]])
    print("  worst:", [(f(when[k]), k[0][:6], round(v, 3), round(fl[k], 2)) for k, v in top[-5:]])

# ---- run-22 check without the double-fill window (live counts it separately) ------------------------------------------------
dkeys = {(w["mint"], w["slot"]) for w in dbl}
print("\n## run 22 check without the double-fill window (both sides)")
for a, b, nm in ((v0, rlib.pk("10-26 02:30"), "A"), (rlib.pk("10-26 02:30"), v1 + 1, "B"), (v0, v1 + 1, "all")):
    X = []
    for seed, rows in R["val"]:
        x = [r for r in rows if a <= r[0] < b and (r[6], r[7]) not in dkeys]
        X.append((sum(r[1] for r in x), sum(1 for r in x if r[1] and r[3] > 0), sum(r[3] for r in x) / 1e9, sum(r[4] for r in x) / 1e9, sum(r[2] for r in x) / 1e9))
    X = np.array(X)
    lw = [w for w in single if a <= w["t"] < b]
    lr = sum(w["pnl"] or 0 for w in lw)
    m, lo_, hi_ = band(X[:, 2])
    print(f"{nm} {fs(a)}-{fs(b)}: replay fills {X[:, 0].mean():.1f} wins {X[:, 1].mean():.1f} realized {m:+.3f} ({lo_:+.3f} to {hi_:+.3f}) fees {X[:, 3].mean():.4f} "
          f"net {X[:, 4].mean():+.3f} ({np.percentile(X[:, 4], 5):+.3f} to {np.percentile(X[:, 4], 95):+.3f}) | live fills {len(lw)} wins {sum(1 for w in lw if (w['pnl'] or 0) > 0)} "
          f"realized {lr:+.4f} -> {(X[:, 2] < lr).mean() * 100:.0f}th pct of replay realized")
    if nm == "all":
        ln = lr - LV["fail_fee"]
        print(f"   all: live net (realized - all failed-try fees {LV['fail_fee']:.4f}) {ln:+.4f} -> {(X[:, 4] < ln).mean() * 100:.0f}th pct of replay net")

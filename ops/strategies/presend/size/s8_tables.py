#!/usr/bin/env python3
"""SIZE study tables (read-only): results.json (s5_run.py), fails.json (s6_fails.py), hours.json (s7_hours.py) -> printed tables
and summary.json. Basis "as run" = realized (engine) + rent back of the token account (1,508,820 lamports per fill) - the run's
failed-try fees (the same at any size: r24-r27 from the flat study's per-window table, r28 from its landing records x 5,120).
Bootstrap = resampling fills (paired: the same fills at both sizes), 5-95 %. Stress = 20 % of later buyers dropped (200 paired draws)."""
import json, collections, time
import numpy as np

D = "/home/moiz/sniper-data/presend_size"
R = json.load(open(f"{D}/results.json"))
T = R["trades"]
R["cut"] = {g: {k: np.array(v) / 1e9 for k, v in c.items()} for g, c in R["cut"].items()}   # lamports -> SOL
RB = 1_508_820
FAILFEE = {"r24": 0.1112, "r25": 0.0531, "r26": 0.1005, "r27": 0.0224, "r28": 15212 * 5120 / 1e9}
SIZES = ["250000000", "350000000", "400000000", "500000000", "650000000"]
RUNS = ("r24", "r25", "r26", "r27", "r28")
rng = np.random.default_rng(2710)
S = {}


def pnl(t, s, lit=False):
    x = t["sz"][s]
    if not x["filled"]: return 0.0
    return (x["lit_pnl"] if lit else x["pnl"]) / 1e9


def boot_sum(d, n=4000):
    d = np.asarray(d); m = d[rng.integers(0, len(d), (n, len(d)))].sum(1)
    return float(np.percentile(m, 5)), float(np.percentile(m, 95))


print("=== pre-send per run x size (as run = realized + rent back - failed-try fees; INFERRED except live) ===")
for run in RUNS:
    X = [t for t in T if t["run"] == run and t["kind"] == "ps"]
    n = len(X); live_s = X[0]["spend_live"]
    gi = [k for k, t in enumerate(T) if t["run"] == run and t["kind"] == "ps"]
    g = "A" if run in ("r24", "r25") else "B"
    gidx = [t["idx"] for t in X]
    S[run] = {}
    live_asrun = sum(t["live"] for t in X) / 1e9 + n * RB / 1e9 - FAILFEE[run]
    print(f"{run} live size {live_s / 1e9:.2f}, {n} fills, live as-run {live_asrun:+.3f} ({live_asrun / n * 1e3:+.2f} mSOL/fill, {live_asrun / n / (live_s / 1e9) * 100:+.2f}% of size), failed-try fees {FAILFEE[run]:.3f}")
    for s in SIZES:
        sz = int(s) / 1e9
        tot = sum(pnl(t, s) for t in X) + n * RB / 1e9 - FAILFEE[run]
        lit = sum(pnl(t, s, True) for t in X) + n * RB / 1e9 - FAILFEE[run]
        f = [t["sz"][s] for t in X]
        wins = sum(1 for y in f if y["filled"] and y["pnl"] > 0)
        cut = np.array(R["cut"][g][s])[:, gidx].sum(1) + n * RB / 1e9 - FAILFEE[run]
        S[run][s] = dict(total=tot, per_fill=tot / n, pct=tot / n / sz * 100, lit=lit, wins=wins, losses=n - wins, po_n=sum(y["po_n"] or 0 for y in f),
                         po_sol=sum(y["po_sol"] or 0 for y in f), rv_n=sum(y["rv_n"] or 0 for y in f), rv_sol=sum(y["rv_sol"] or 0 for y in f),
                         flats=sum(1 for y in f if y["flat"]), lit_flats=sum(1 for y in f if y["lit_flat"]), cut_mean=float(cut.mean()),
                         cut_p5=float(np.percentile(cut, 5)), cut_p95=float(np.percentile(cut, 95)),
                         exits=dict(collections.Counter(y["why"] for y in f)))
        x = S[run][s]
        print(f"   {sz:.2f}: {x['total']:+.3f} | {x['per_fill'] * 1e3:+.2f} mSOL/fill | {x['pct']:+.2f}% | lit {x['lit']:+.3f} | W/L {x['wins']}/{x['losses']} | priced out {x['po_n']} ({x['po_sol']:.2f} SOL) | revived {x['rv_n']} ({x['rv_sol']:.2f}) | flats {x['flats']} (lit {x['lit_flats']}) | cut20 {x['cut_mean']:+.3f} [{x['cut_p5']:+.3f}, {x['cut_p95']:+.3f}]")
    # paired size differences
    for a, b in (("500000000", "350000000"), ("350000000", "250000000"), ("650000000", "500000000")):
        d = [pnl(t, a) - pnl(t, b) for t in X]
        lo, hi = boot_sum(d)
        cd = (np.array(R["cut"][g][a]) - np.array(R["cut"][g][b]))[:, gidx].sum(1)
        S[run][f"d_{a}_{b}"] = dict(d=float(sum(d)), lo=lo, hi=hi, per_fill=float(np.mean(d)), cut_mean=float(cd.mean()), cut_p5=float(np.percentile(cd, 5)), cut_p95=float(np.percentile(cd, 95)),
                                    n_pos=int(sum(1 for x in d if x > 1e-12)), n_neg=int(sum(1 for x in d if x < -1e-12)))
        y = S[run][f"d_{a}_{b}"]
        print(f"   delta {int(a) / 1e9:.2f}-{int(b) / 1e9:.2f}: {y['d']:+.3f} [{lo:+.3f}, {hi:+.3f}] ({y['per_fill'] * 1e3:+.2f} mSOL/fill; fills better/worse {y['n_pos']}/{y['n_neg']}); with 20% fewer buyers {y['cut_mean']:+.3f} [{y['cut_p5']:+.3f}, {y['cut_p95']:+.3f}]")

print("\n=== pooled ===")
X = [t for t in T if t["kind"] == "ps"]
for grp, runs in (("0.50 runs (r26, r28)", ("r26", "r28")), ("0.34/0.35 runs (r24, r25, r27)", ("r24", "r25", "r27")), ("all 5", RUNS)):
    Y = [t for t in X if t["run"] in runs]
    line = f"{grp}: fills {len(Y)}"
    for s in SIZES:
        line += f" | {int(s) / 1e9:.2f} {sum(pnl(t, s) for t in Y) + len(Y) * RB / 1e9 - sum(FAILFEE[r] for r in runs):+.3f}"
    d = [pnl(t, "500000000") - pnl(t, "350000000") for t in Y]
    lo, hi = boot_sum(d)
    # cut: paired across runs, per draw
    cd = 0
    for g in ("A", "B"):
        gidx = [t["idx"] for t in Y if t["g"] == g]
        if gidx: cd = cd + (np.array(R["cut"][g]["500000000"]) - np.array(R["cut"][g]["350000000"]))[:, gidx].sum(1)
    line += f" || 0.50-0.35 {sum(d):+.3f} [{lo:+.3f}, {hi:+.3f}], cut20 {np.mean(cd):+.3f} [{np.percentile(cd, 5):+.3f}, {np.percentile(cd, 95):+.3f}]"
    # best size by bootstrap
    M = np.array([[pnl(t, s) for s in SIZES] for t in Y])
    bi = M[rng.integers(0, len(Y), (4000, len(Y)))].sum(1).argmax(1)
    line += " | best-size share " + ", ".join(f"{int(SIZES[k]) / 1e9:.2f}:{(bi == k).mean() * 100:.0f}%" for k in range(len(SIZES)))
    print(line)
    S["pool_" + grp] = line

print("\n=== regular (realized basis) ===")
for run in RUNS:
    Y = [t for t in T if t["run"] == run and t["kind"] == "reg"]
    if not Y: continue
    line = f"{run} reg n={len(Y)} live({Y[0]['spend_live'] / 1e9:.2f}) {sum(t['live'] for t in Y) / 1e9:+.3f}"
    for s in SIZES:
        line += f" | {int(s) / 1e9:.2f} {sum(pnl(t, s) for t in Y):+.3f} (po {sum(t['sz'][s]['po_n'] or 0 for t in Y)}, rv {sum(t['sz'][s]['rv_n'] or 0 for t in Y)})"
    print(line); S[f"reg_{run}"] = line

print("\n=== same-hour size effect (replay, pre-send, PKT hour of the fill): 0.50 - 0.35 ===")
H = collections.defaultdict(list)
for t in X:
    h = int(time.strftime("%H", time.gmtime(t["t"] / 1e9 + 18000)))
    H[h].append((t["run"], pnl(t, "500000000") - pnl(t, "350000000"), pnl(t, "350000000")))
hours = {}
for h in sorted(H):
    d = [x[1] for x in H[h]]
    lo, hi = boot_sum(d, 2000)
    hours[h] = dict(n=len(d), d=float(sum(d)), per_fill=float(np.mean(d)), lo=lo, hi=hi, runs=sorted({x[0] for x in H[h]}))
    print(f"  {h:02d}h n={len(d):3d} delta {sum(d):+.4f} [{lo:+.4f}, {hi:+.4f}] per fill {np.mean(d) * 1e3:+.2f} mSOL  runs {','.join(hours[h]['runs'])}")
neg = [h for h, v in hours.items() if v["d"] < 0]
print("hours where 0.50 < 0.35:", neg, "of", len(hours))
S["hours"] = hours

print("\n=== failed slippage buys in holds (MEASURED; pass columns INFERRED) ===")
F = json.load(open(f"{D}/fails.json"))
fills = {r: len([t for t in X if t["run"] == r]) for r in RUNS}
for run in RUNS:
    Y = [o for o in F if o["run"] == run]; nd = [o for o in Y if not o["dup"]]
    mm = np.array([o["miss_live"] for o in nd if o["miss_live"] is not None])
    small = [o for o in nd if o["miss_live"] is not None and o["miss_live"] < 1.0]
    S[f"fails_{run}"] = dict(n=len(Y), nd=len(nd), per_fill=len(Y) / fills[run], holds=len({(o['mint'], o['t']) for o in nd}), med_miss=float(np.median(mm)),
                             under1=len(small), p25=sum(o["pass_25"] for o in nd), p25_sol=sum(o["sol"] or 0 for o in nd if o["pass_25"]),
                             p35=sum(o["pass_35"] for o in nd), p35_sol=sum(o["sol"] or 0 for o in nd if o["pass_35"]), p50=sum(o["pass_50"] for o in nd))
    x = S[f"fails_{run}"]
    print(f"{run}: {x['n']} failed ({x['per_fill']:.2f}/fill), {x['nd']} not dup in {x['holds']} holds; median miss {x['med_miss']:.1f}%; missed by <1%: {x['under1']}; pass at 0.25 {x['p25']} ({x['p25_sol']:.2f} SOL), 0.35 {x['p35']} ({x['p35_sol']:.2f}), 0.50 {x['p50']}")
json.dump(S, open(f"{D}/summary.json", "w"), indent=1, default=float)

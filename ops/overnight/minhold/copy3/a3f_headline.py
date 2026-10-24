#!/usr/bin/env python3
# headline tables for the report: copy first buy, sell T ms after their first sell (mirror_first), optional price guard g;
# per wallet and combined; fills, win, total, per fill, profit factor, max drawdown, per day, per run. -> out/headline.txt / .json
import os, sys, json, gzip, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
D = pickle.load(gzip.open(os.path.join(lib3.HERE, "out/copy_rows.pkl.gz"), "rb")); N = D["names"]; RW = D["rows"]
WS = ["Fsb6Ns75", "pXGQ6J2z", "4vw54BmA"]; HOURS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}; FAIL = 0.0005
G = collections.defaultdict(list)
for r in RW: G[(r["w"], r["run"], r["T"], r["B"], r["var"])].append(r)
def series(rows, ri, g, exg=False):
    p = []
    for r in sorted(rows, key=lambda r: r["bt"]):
        if g is not None and r["entry_vs_them"] > 1 + g: p.append((False, -FAIL)); continue
        if exg and ri in r["grad_rules"]: continue
        p.append((True, r["pnl"][ri]))
    return p
def st(p, hrs):
    f = [x for ok, x in p if ok]; tot = sum(x for _, x in p)
    w = [x for x in f if x > 0]; l = [x for x in f if x <= 0]
    cum = mx = dd = 0.0
    for _, x in p: cum += x; mx = max(mx, cum); dd = max(dd, mx - cum)
    return dict(fills=len(f), tries=len(p), win=len(w) / len(f) if f else 0, tot=tot, per=(sum(f) / len(f)) if f else 0, pf=(sum(w) / -sum(l)) if l and sum(l) < 0 else 99.0, dd=dd, day=tot / hrs * 24)
OUT = {}; L = []
for rn in ("mirror_first", "mirror_last"):
    ri = N.index(rn)
    for var in ("slip", "drop2", "all"):
        for T in (35, 75, 150):
            for g in (None, 0.02, 0.05):
                for B in (0.5, 1.0, 2.0):
                    for w in WS + ["ALL"]:
                        ws = WS if w == "ALL" else [w]
                        runs = {run: st(series([r for x in ws for r in G[(x, run, T, B, var)]], ri, g), HOURS[run]) for run in ("R2", "R3", "R1")}
                        allp = series([r for x in ws for run in ("R1", "R2", "R3") for r in G[(x, run, T, B, var)]], ri, g)
                        a = st(allp, sum(HOURS.values())); eg = st(series([r for x in ws for run in ("R1", "R2", "R3") for r in G[(x, run, T, B, var)]], ri, g, exg=True), sum(HOURS.values()))
                        k = f"{rn}|{var}|{T}|{g}|{B}|{w}"; OUT[k] = dict(all=a, runs=runs, ex_grad=eg)
                        if rn == "mirror_first" and B == 1.0 and var in ("slip", "drop2"):
                            gs = "none" if g is None else f"+{int(g * 100)}%"
                            L.append(f"{var:5s} T={T:3d} guard {gs:4s} {w:8s} | fills {a['fills']:3d}/{a['tries']:3d} win {a['win']:4.0%} tot {a['tot']:+6.2f} per fill {a['per']:+.3f} PF {a['pf']:4.2f} maxDD {a['dd']:5.2f} /day {a['day']:+5.2f} | "
                                     + " ".join(f"{run} {v['tot']:+5.2f}" for run, v in runs.items()) + f" | excl grad {eg['tot']:+.2f}")
json.dump(OUT, open(os.path.join(lib3.HERE, "out/headline.json"), "w"))
open(os.path.join(lib3.HERE, "out/headline.txt"), "w").write("\n".join(L) + "\n")
print("\n".join(L))

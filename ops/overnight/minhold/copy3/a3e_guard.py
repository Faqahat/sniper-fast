#!/usr/bin/env python3
# price-guard detail: mirror_first, fill only if our price <= (1+g) x their fill; per wallet, run, latency, size, follower variant;
# fills, total, per fill, win rate, and the same without graduated (flagged) exits. -> out/guard.json / out/guard.txt
import os, sys, json, gzip, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
D = pickle.load(gzip.open(os.path.join(lib3.HERE, "out/copy_rows.pkl.gz"), "rb")); N = D["names"]; RW = D["rows"]
WS = ["Fsb6Ns75", "pXGQ6J2z", "4vw54BmA"]; HOURS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}; FAIL = 0.0005
G = collections.defaultdict(list)
for r in RW: G[(r["w"], r["run"], r["T"], r["B"], r["var"])].append(r)
L = []; OUT = {}
def one(rows, g, ri, exg=False):
    f = [r for r in rows if r["entry_vs_them"] <= 1 + g and not (exg and ri in r["grad_rules"])]
    p = [r["pnl"][ri] for r in f]; nf = sum(1 for r in rows if r["entry_vs_them"] > 1 + g)
    tot = sum(p) - nf * FAIL
    return dict(fills=len(p), of=len(rows), tot=tot, per=(sum(p) / len(p)) if p else 0, win=(sum(1 for x in p if x > 0) / len(p)) if p else 0, grad=sum(1 for r in f if ri in r["grad_rules"]))
for rn in ("mirror_first", "mirror_last", "time60", "tp20_sl10_t120"):
    ri = N.index(rn)
    for var in ("slip", "drop2"):
        for T in (35, 75, 150):
            for g in (0.01, 0.02, 0.03, 0.05):
                for B in (0.5, 1.0, 2.0):
                    for w in WS + ["ALL"]:
                        ws = WS if w == "ALL" else [w]
                        res = {run: one([r for x in ws for r in G[(x, run, T, B, var)]], g, ri) for run in ("R2", "R3", "R1")}
                        allr = [r for x in ws for run in ("R1", "R2", "R3") for r in G[(x, run, T, B, var)]]
                        ex = one(allr, g, ri, exg=True); tot = sum(v["tot"] for v in res.values())
                        OUT[f"{rn}|{var}|{T}|{g}|{B}|{w}"] = dict(runs=res, total=tot, per_day=tot / sum(HOURS.values()) * 24, ex_grad=ex["tot"])
                        if B == 1.0 and rn == "mirror_first":
                            L.append(f"{rn} {var:5s} T={T:3d} g={int(g*100)}% B={B} {w:8s} | " + " | ".join(f"{run} {v['fills']:3d}/{v['of']:3d} fills {v['tot']:+6.2f} ({v['per']:+.3f}/fill, win {v['win']:.0%})" for run, v in res.items())
                                     + f" | total {tot:+6.2f} = {tot / sum(HOURS.values()) * 24:+.2f}/day | excl grad {ex['tot']:+.2f}")
json.dump(OUT, open(os.path.join(lib3.HERE, "out/guard.json"), "w"))
open(os.path.join(lib3.HERE, "out/guard.txt"), "w").write("\n".join(L) + "\n")
print("\n".join(L))

#!/usr/bin/env python3
# copy replay, part 2: (1) the a-priori exits (mirror first sell / mirror last sell) per run, (2) a price guard: we only fill if our price
# is at most (1+g) x their fill price (else the buy fails, cost 0.0005 SOL) — g chosen on R2, tested on R3 and R1; (3) the same with graduated
# (flagged) exits removed; (4) the share of the copy profit that sits in a few big winners.
import os, sys, json, gzip, pickle, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
D = pickle.load(gzip.open(os.path.join(lib3.HERE, "out/copy_rows.pkl.gz"), "rb")); N = D["names"]; RW = D["rows"]
HOURS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}; WS = ["Fsb6Ns75", "pXGQ6J2z", "4vw54BmA"]; FAIL = 0.0005
G = collections.defaultdict(list)
for r in RW: G[(r["w"], r["run"], r["T"], r["B"], r["var"])].append(r)
def sel(w, runs, T, B, var): return [r for run in runs for ww in ([w] if w != "ALL" else WS) for r in G[(ww, run, T, B, var)]]
def pnls(rows, ri, guard=None, ex_grad=False):
    out = []
    for r in sorted(rows, key=lambda r: r["bt"]):
        if ex_grad and ri in r["grad_rules"]: continue
        if guard is not None and r["entry_vs_them"] > 1 + guard: out.append(-FAIL); continue
        out.append(r["pnl"][ri])
    return out
def st(p, runs):
    if not p: return dict(n=0, tot=0.0)
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    cum = mx = dd = 0.0
    for x in p: cum += x; mx = max(mx, cum); dd = max(dd, mx - cum)
    hrs = sum(HOURS[r] for r in runs)
    return dict(n=len(p), win=len(w) / len(p), tot=sum(p), per=sum(p) / len(p), pf=(sum(w) / -sum(l)) if sum(l) < 0 else 99.0, dd=dd, day=sum(p) / hrs * 24,
                top5=sum(sorted(p)[-5:]))
def f(s): return "n=0" if not s["n"] else f"n={s['n']:3d} win {s['win']:4.0%} tot {s['tot']:+6.2f} per {s['per']:+.4f} PF {s['pf']:4.2f} DD {s['dd']:5.2f} /day {s['day']:+6.2f} (top5 {s['top5']:+.2f})"
L = []; OUT = {}
pr = lambda *a: L.append(" ".join(str(x) for x in a))
for rn in ("mirror_first", "mirror_last"):
    ri = N.index(rn)
    for var in ("all", "slip", "drop2"):
        pr(f"\n## {rn}, variant {var}: per run (R2 / R3 / R1), B = 1 SOL; then excl. graduated exits")
        for w in WS + ["ALL"]:
            for T in (35, 75, 150, 300):
                ss = {run: st(pnls(sel(w, [run], T, 1.0, var), ri), [run]) for run in ("R2", "R3", "R1")}
                sg = st(pnls(sel(w, ["R1", "R2", "R3"], T, 1.0, var), ri, ex_grad=True), ["R1", "R2", "R3"])
                OUT[f"{rn}_{var}_{w}_{T}"] = dict(runs=ss, all_ex_grad=sg)
                pr(f"{w:8s} T={T:3d} | R2 {f(ss['R2'])} | R3 {f(ss['R3'])} | R1 {f(ss['R1'])} | all runs excl grad {sg['tot']:+.2f} ({sg['n']})")
pr("\n## size: mirror_first, all three runs, variant slip, per B (total SOL, per trade, per day)")
for w in WS + ["ALL"]:
    for T in (35, 75):
        pr(f"{w:8s} T={T:3d} " + " | ".join(f"B={B}: {st(pnls(sel(w, ['R1','R2','R3'], T, B, 'slip'), N.index('mirror_first')), ['R1','R2','R3'])['tot']:+.2f} ({st(pnls(sel(w, ['R1','R2','R3'], T, B, 'slip'), N.index('mirror_first')), ['R1','R2','R3'])['per']:+.4f}/trade)" for B in (0.25, 0.5, 1.0, 2.0)))
pr("\n## price guard (fill only if our price <= (1+g) x theirs) with mirror_first; g chosen on R2 (B = 1), tested on R3 and R1")
GS = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, None]
for var in ("all", "slip", "drop2"):
    for w in WS + ["ALL"]:
        for T in (35, 75, 150):
            ri = N.index("mirror_first")
            tr2 = sel(w, ["R2"], T, 1.0, var)
            if not tr2: continue
            best = max(GS, key=lambda g: st(pnls(tr2, ri, g), ["R2"])["tot"])
            s2 = st(pnls(tr2, ri, best), ["R2"]); s3 = st(pnls(sel(w, ["R3"], T, 1.0, var), ri, best), ["R3"]); s1 = st(pnls(sel(w, ["R1"], T, 1.0, var), ri, best), ["R1"])
            filled3 = sum(1 for r in sel(w, ["R3"], T, 1.0, var) if best is None or r["entry_vs_them"] <= 1 + best)
            OUT[f"guard_{var}_{w}_{T}"] = dict(g=best, R2=s2, R3=s3, R1=s1, filled_R3=filled3)
            pr(f"{var:5s} {w:8s} T={T:3d} guard {('+' + str(int(best * 100)) + '%') if best is not None else 'none':5s} | R2 {f(s2)} | R3 {f(s3)} (filled {filled3}) | R1 {f(s1)}")
pr("\n## guard sweep on ALL wallets, mirror_first, T=75, variant slip, every run (to see the shape, not a choice)")
for g in GS:
    pr(f"  guard {('+' + str(int(g * 100)) + '%') if g is not None else 'none':5s} " + " | ".join(f"{run} {st(pnls(sel('ALL', [run], 75, 1.0, 'slip'), N.index('mirror_first'), g), [run])['tot']:+6.2f}" for run in ("R2", "R3", "R1")))
json.dump(OUT, open(os.path.join(lib3.HERE, "out/copy_eval2.json"), "w"), indent=1)
open(os.path.join(lib3.HERE, "out/copy_eval2.txt"), "w").write("\n".join(L) + "\n")
print("\n".join(L))

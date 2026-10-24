#!/usr/bin/env python3
# evaluate the copy replay (out/copy_rows.pkl.gz): fixed exits, followers ahead of us, and rule choice on R2 -> test on R3 and R1
import os, sys, json, gzip, pickle, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
D = pickle.load(gzip.open(os.path.join(lib3.HERE, "out/copy_rows.pkl.gz"), "rb")); N = D["names"]; RW = D["rows"]
HOURS = {"R1": 14.9, "R2": 21.8, "R3": 24.0}
WS = ["Fsb6Ns75", "pXGQ6J2z", "4vw54BmA"]
def stats(rows, ri, ex_grad=False):
    v = sorted(((r["bt"], r["pnl"][ri]) for r in rows if not (ex_grad and ri in r["grad_rules"])))
    p = [x for _, x in v]
    if not p: return dict(n=0)
    w = [x for x in p if x > 0]; l = [x for x in p if x <= 0]
    cum = mx = dd = 0.0
    for x in p: cum += x; mx = max(mx, cum); dd = max(dd, mx - cum)
    hrs = sum(HOURS[r] for r in {r["run"] for r in rows})
    return dict(n=len(p), win=len(w) / len(p), tot=sum(p), per=sum(p) / len(p), pf=(sum(w) / -sum(l)) if l and sum(l) < 0 else float("inf"),
                dd=dd, day=sum(p) / hrs * 24, grad=sum(1 for r in rows if ri in r["grad_rules"]), end=sum(1 for r in rows if ri in r["end_rules"]))
def fmt(s):
    if not s.get("n"): return "n=0"
    return f"n={s['n']:3d} win {s['win']:4.0%} tot {s['tot']:+7.2f} per {s['per']:+.4f} PF {s['pf']:4.2f} DD {s['dd']:5.2f} /day {s['day']:+6.2f}" + (f" grad{s['grad']}" if s.get("grad") else "")
G = collections.defaultdict(list)
for r in RW: G[(r["w"], r["run"], r["T"], r["B"], r["var"])].append(r)
def sel(w, runs, T, B, var): return [r for run in runs for ww in ([w] if w != "ALL" else WS) for r in G[(ww, run, T, B, var)]]
out = {}; lines = []
P = lambda *a: lines.append(" ".join(str(x) for x in a))
# 1. followers ahead of us
P("## buyers that land between their first buy and our fill (median / mean / % with >=1), entry price vs theirs (median)")
for w in WS:
    for T in (0, 35, 75, 150, 300):
        v = sel(w, ["R1", "R2", "R3"], T, 1.0, "all")
        if not v: continue
        a = [r["n_ahead_buy"] for r in v]; e = [r["entry_vs_them"] for r in v]; sb = [r["ahead_buy_sol"] for r in v]
        P(f"{w} T={T:3d}ms n={len(v)} ahead buys med {statistics.median(a):.0f} mean {statistics.mean(a):.1f} >=1: {sum(1 for x in a if x >= 1) / len(a):.0%}  ahead SOL med {statistics.median(sb):.2f} | our price vs theirs med {statistics.median(e):.3f} p75 {statistics.quantiles(e, n=4)[2]:.3f}")
        out[f"ahead_{w}_{T}"] = dict(med=statistics.median(a), mean=statistics.mean(a), ge1=sum(1 for x in a if x >= 1) / len(a), entry_med=statistics.median(e), ahead_sol_med=statistics.median(sb))
# 2. fixed exits, all runs, per T and B
FIX = ["mirror_first", "mirror_last", "time20", "time60", "time120", "time300", "tp20_sl10_t120", "tp10_sl5_t60", "tp50_sl20_t300"]
for var in ("all", "drop2", "slip"):
    P(f"\n## fixed exits, all runs, variant={var}")
    for w in WS + ["ALL"]:
        for T in (0, 35, 75, 150, 300):
            if T == 0 and var != "all": continue
            for B in (0.25, 1.0, 2.0):
                v = sel(w, ["R1", "R2", "R3"], T, B, var)
                if not v: continue
                for rn in FIX[:4]:
                    s = stats(v, N.index(rn)); out[f"fix_{var}_{w}_{T}_{B}_{rn}"] = s
                    P(f"{w:8s} T={T:3d} B={B:4.2f} {rn:14s} {fmt(s)}")
# 3. choose on R2, test on R3 and R1 (per wallet, per T, per B, per variant); also the best rule among all on the test day (hindsight, labelled)
P("\n## rule chosen on R2 (best total, n>=15) -> R3 and R1 (out-of-sample). 'hind' = best rule on R3 itself (hindsight, NOT a result)")
for var in ("all", "drop2", "slip"):
    for w in WS + ["ALL"]:
        for T in (35, 75, 150, 300):
            for B in (0.25, 0.5, 1.0, 2.0):
                tr_ = sel(w, ["R2"], T, B, var)
                if len(tr_) < 15: continue
                best = max(range(len(N)), key=lambda ri: stats(tr_, ri)["tot"])
                s2 = stats(tr_, best); s3 = stats(sel(w, ["R3"], T, B, var), best); s1 = stats(sel(w, ["R1"], T, B, var), best)
                h3 = max(range(len(N)), key=lambda ri: stats(sel(w, ["R3"], T, B, var), ri)["tot"]); sh = stats(sel(w, ["R3"], T, B, var), h3)
                out[f"sel_{var}_{w}_{T}_{B}"] = dict(rule=N[best], R2=s2, R3=s3, R1=s1, hind_rule=N[h3], hind=sh)
                P(f"{var:5s} {w:8s} T={T:3d} B={B:4.2f} rule {N[best]:22s} | R2 {fmt(s2)} | R3 {fmt(s3)} | R1 {fmt(s1)} | hind R3 {N[h3]} {sh.get('tot', 0):+.2f}")
# 4. how many rules are positive on both R2 and R3 (luck check) at T=75, B=1
P("\n## share of the rules positive on R2 that are also positive on R3 (T=75 ms, B=1, all followers kept)")
for w in WS + ["ALL"]:
    a = sel(w, ["R2"], 75, 1.0, "all"); b = sel(w, ["R3"], 75, 1.0, "all")
    if not a or not b: continue
    pos2 = [ri for ri in range(len(N)) if stats(a, ri)["tot"] > 0]; both = [ri for ri in pos2 if stats(b, ri)["tot"] > 0]
    pos3 = [ri for ri in range(len(N)) if stats(b, ri)["tot"] > 0]
    P(f"{w}: rules {len(N)} | positive on R2 {len(pos2)} | of those positive on R3 {len(both)} | positive on R3 at all {len(pos3)}")
    out[f"luck_{w}"] = dict(rules=len(N), pos2=len(pos2), both=len(both), pos3=len(pos3))
json.dump(out, open(os.path.join(lib3.HERE, "out/copy_eval.json"), "w"), indent=1)
open(os.path.join(lib3.HERE, "out/copy_eval.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

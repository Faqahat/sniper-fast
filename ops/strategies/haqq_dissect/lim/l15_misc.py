#!/usr/bin/env python3
"""LIM step 15 (read-only): (a) same-dump pairs (his DIP fill vs our fire on the same dump), (b) his behind-crowd fills on dumps
we fired / did not fire (engine on) / engine off, (c) his tier rule and his size on our fires, (d) fires a looser guard would block.
Out: data/lim/l15.txt"""
import pickle, json, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from runs import run_files
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
CF, CX = 3.52e-3, 0.53e-3
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
H = [r for r in pickle.load(open(f"{OUT}/hfeat.pkl", "rb")) if not r["mayhem"]]
FCl = pickle.load(open(f"{OUT}/fires_cf.pkl", "rb")); FC = {(r["run"], r["us"]): r for r in FCl}
pairs = [(h, FC[h["ours"]]) for h in H if h.get("ours") and h["ours"] in FC]
P("## (a) same dump: his DIP fill vs our fire (%/SOL before tx costs; ours = no-guard counterfactual at our measured position)")
for nm, sel in (("all", lambda h, f: True), ("we filled", lambda h, f: f["out"] == "fill"), ("we failed (+5%)", lambda h, f: f["out"] == "fail")):
    v = [(h, f) for h, f in pairs if sel(h, f)]
    hs = sum(h["spend"] for h, f in v); fs = sum(f["spend"] for h, f in v)
    P(f"- {nm}: n {len(v)}; his pr p50 {np.median([h['pr'] for h, f in v]):.3f}, buys ahead p50 {np.median([h['nb_ahead'] for h, f in v]):.0f}, ms {np.median([h['d_ms'] for h, f in v]):.0f}; "
      f"his actual {100*sum(h['lot_pnl'] for h, f in v)/hs:+.2f}%, his h5 {100*sum(h['rep'][(5,1.0)] for h, f in v)/hs:+.2f}%, h15 {100*sum(h['rep'][(15,1.0)] for h, f in v)/hs:+.2f}% | "
      f"ours need p50 {np.median([f['need'] for h, f in v]):.3f}, ours h5 {100*sum(f['pn'][(5,1.0)] for h, f in v)/fs:+.2f}%, h15 {100*sum(f['pn'][(15,1.0)] for h, f in v)/fs:+.2f}%; we landed first {100*np.mean([tuple(f['us']) < (h['s'], h['i']) for h, f in v]):.0f}%")
win = []
for run, f in run_files().items():
    ts = []
    for l in open(f):
        try: d = json.loads(l)
        except Exception: continue
        t = d.get("t")
        if t: ts.append(t / 1e9 if t > 1e15 else t)
    if ts: win.append((min(ts), max(ts)))
inrun = lambda t: any(a <= t <= b for a, b in win)
s = lambda v, k: 100 * sum(r["rep"][k] for r in v) / sum(r["spend"] for r in v) if v else float("nan")
a = lambda v: 100 * sum(r["lot_pnl"] for r in v) / sum(r["spend"] for r in v) if v else float("nan")
P("\n## (b) his DIP fills by price paid: on dumps we fired / engine on but no fire / engine off (h5 replay and actual, %/SOL)")
for nm, sel in (("pr<=1.05", lambda r: r["pr"] <= 1.05), ("pr 1.05-1.10", lambda r: 1.05 < r["pr"] <= 1.10), ("pr 1.10-1.20", lambda r: 1.10 < r["pr"] <= 1.20), ("pr>1.05", lambda r: r["pr"] > 1.05)):
    v = [r for r in H if sel(r)]
    g1 = [r for r in v if r.get("ours")]; g2 = [r for r in v if not r.get("ours") and inrun(r["bt"])]; g3 = [r for r in v if not inrun(r["bt"])]
    P(f"- {nm}: we fired n {len(g1)} h5 {s(g1,(5,1.0)):+.2f} act {a(g1):+.2f} | engine on, no fire n {len(g2)} h5 {s(g2,(5,1.0)):+.2f} act {a(g2):+.2f} | engine off n {len(g3)} h5 {s(g3,(5,1.0)):+.2f} act {a(g3):+.2f}")
B = pickle.load(open(f"{OUT}/fires_cf_s0.3.pkl", "rb"))
tot = lambda R, g, fo=1.0: sum((r["pn"][(r["hold"], fo)] - CF) if r["need"] <= 1 + g + 1e-9 else -CX for r in R)
P("\n## (c) our fires, net SOL (exit ours): live size vs haqq's 0.30 size; his tier rule")
for nm, R in (("live size 0.35-0.55", FCl), ("0.30 SOL", B)):
    P(f"- {nm}: +5% {tot(R,0.05):+.3f}, +10% {tot(R,0.10):+.3f}, +15% {tot(R,0.15):+.3f}, none {tot(R,9.0):+.3f} (fol 0.8 none {tot(R,9.0,0.8):+.3f})")
his = sum(((r["pn"][(r["hold"], 1.0)] - CF) if (r["spend"] <= 0.45 or r["need"] <= 1.087) else -CX) for r in FCl)
P(f"- his tier rule (<=0.45 SOL no limit, 0.5+ 8%): {his:+.3f}; his big-buy 2% rule: {tot(FCl,0.0204):+.3f}; 5% rule {tot(FCl,0.0526):+.3f}")
R = sorted(FCl, key=lambda r: (r["srv"], r["us"][0]))
P("\n## (d) a converted fill blocks the next fire on the same server inside its hold (one position at a time; live: 0 such after real fills)")
net = lambda r, g: (r["pn"][(r["hold"], 1.0)] - CF) if r["need"] <= 1 + g + 1e-9 else -CX
for g in (0.10, 0.15, 0.20, 9.0):
    adj = 0; n = 0
    for x, y in zip(R, R[1:]):
        if x["srv"] == y["srv"] and y["ds"] - x["us"][0] <= x["hold"] + 1 and 1.05 < x["need"] <= 1 + g: adj -= net(y, g); n += 1
    P(f"- guard {g:g}: blocked fires {n}, adjustment {adj:+.3f} SOL")
open(f"{OUT}/l15.txt", "w").write("\n".join(out) + "\n")

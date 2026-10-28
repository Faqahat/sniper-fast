#!/usr/bin/env python3
"""Example trades (D1) for every claim in REPORT.md: GMGN token links + solscan tx links. Out: x11.txt"""
import sys, pickle, random
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
random.seed(7)
LL = {l["lot_id"]: l for l in X.lots()}
r1 = [r for r in pickle.load(open(f"{X.X}/x1.pkl", "rb")) if r["day"] == "D1" and "ms" in r]
R4 = {r["lot"]: r for r in pickle.load(open(f"{X.X}/x4.pkl", "rb"))}
cop = pickle.load(open(f"{X.X}/x6.pkl", "rb"))["D1"]["cop"]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
def lk(sig, t="tx"): return f"[{t}]({X.ss(sig)})"
def tk(m): return f"[{m[:8]}]({X.gm(m)})"
P("### A. same-slot landings (T in his own slot, he lands after it)")
for r in random.sample([r for r in r1 if r["gap"] == 0 and 40 <= r["igap"] <= 200], 6):
    P(f"- {X.pkt(LL[r['lot']]['bt'])} {r['bot']} {tk(r['mint'])}: trigger {'buy' if r['tbuy'] else 'sell'} {r['tsol']:.2f} SOL {lk(r['tsig'],'T')} idx {r['ti']} -> his buy {lk(r['sig'],'buy')} idx {r['i']} same slot {r['s']}, +{r['igap']} idx, {r['ms']:.0f} ms, leader {r['client']}, copy {r['copy']}")
P("### B. next-slot landings (T late in its block)")
for r in random.sample([r for r in r1 if r["gap"] == 1 and r["tfrac"] > 0.8], 6):
    P(f"- {X.pkt(LL[r['lot']]['bt'])} {r['bot']} {tk(r['mint'])}: T at {100*r['tfrac']:.0f}% of block {lk(r['tsig'],'T')} -> his buy {lk(r['sig'],'buy')} next slot at {100*r['frac']:.0f}% of block, {r['ms']:.0f} ms, leader {r['client']}, copy {r['copy']}")
P("### C. the few very-close same-slot landings (index gap <= 25)")
for r in [r for r in r1 if r["gap"] == 0 and r["igap"] <= 25][:6]:
    P(f"- {r['bot']} {tk(r['mint'])}: T {lk(r['tsig'],'T')} idx {r['ti']} -> his buy {lk(r['sig'],'buy')} idx {r['i']} (+{r['igap']}), leader {r['client']}, copy {r['copy']}")
P("### D. exits next to the sibling's sell (same slot)")
k = 0
for lot, r in R4.items():
    if r["day"] != "D1" or not r["sells"] or k >= 6: continue
    s0 = r["sells"][0]
    sib = [p for p in r["path"] if p[7] and not p[3] and p[0] == s0["s"]]
    if sib and random.random() < 0.05:
        k += 1; P(f"- {r['bot']} {tk(r['mint'])}: his sell {lk(s0['sig'],'sell')} idx {s0['i']} / Grozoe sell {lk(sib[0][8],'sib sell')} idx {sib[0][1]} same slot {s0['s']} ({'Grozoe first' if sib[0][1] < s0['i'] else 'he first'}), P&L {r['pnl']:+.3f}")
P("### E. 30-min timeout exits")
for r in [r for r in R4.values() if r["day"] == "D1" and r["sells"] and 1799 <= r["sells"][0]["dbt"] <= 1802][:6]:
    P(f"- {r['bot']} {tk(r['mint'])} buy {lk(r['buy_sig'],'buy')} sell {lk(r['sells'][0]['sig'],'sell')} hold {r['sells'][0]['dbt']} s, price x{r['sells'][0]['r']:.2f}, P&L {r['pnl']:+.3f}")
P("### F. winners sold near the peak (exit/peak >= 0.97, P&L >= 0.3)")
w = [r for r in R4.values() if r["day"] == "D1" and r["sells"] and r["pnl"] >= 0.3 and r["sells"][0]["r"] / r["sells"][0]["rpeak"] >= 0.97]
for r in sorted(w, key=lambda r: -r["pnl"])[:6]:
    s0 = r["sells"][0]; P(f"- {r['bot']} {tk(r['mint'])} buy {lk(r['buy_sig'],'buy')} sell {lk(s0['sig'],'sell')} hold {s0['dbt']} s, exit price x{s0['r']:.2f} vs peak x{s0['rpeak']:.2f}, last trade before his sell: {'buy' if s0['last_buy'] else 'sell'} {s0['last_sol'] or 0:.2f} SOL, P&L {r['pnl']:+.3f}")
P("### G. copiers buying right after him and selling right after him")
k = 0
for lot, r in R4.items():
    if r["day"] != "D1" or not r["sells"] or k >= 6: continue
    s0 = r["sells"][0]
    cb = [p for p in r["path"] if p[2] in cop and p[2] != X.SIB and p[3] and p[0] - r["s"] <= 1]
    cs = [p for p in r["path"] if p[2] in cop and p[2] != X.SIB and not p[3] and (p[0], p[1]) > (s0["s"], s0["i"]) and p[0] - s0["s"] <= 2]
    if cb and cs and random.random() < 0.05:
        k += 1; P(f"- {r['bot']} {tk(r['mint'])}: his buy {lk(r['buy_sig'],'buy')} slot {r['s']} idx {r['i']} -> {cb[0][2][:6]} buys {cb[0][4]:.2f} SOL {lk(cb[0][8],'copy buy')} slot {cb[0][0]} idx {cb[0][1]}; his sell {lk(s0['sig'],'sell')} slot {s0['s']} -> {cs[0][2][:6]} sells {lk(cs[0][8],'copy sell')} slot {cs[0][0]}, his P&L {r['pnl']:+.3f}")
open(f"{X.X}/x11.txt", "w").write("\n".join(out) + "\n")

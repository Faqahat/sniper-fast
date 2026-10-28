#!/usr/bin/env python3
"""8yYMhu step 8 (read-only): exact per-bot P&L for the 24 h window, cash view (every in-window lamport of a buy / sell / failed tx assigned
via its lot to a bot; failed attempts that never filled = 'failed attempts, no fill'); sums to the reconciled trading NET to the lamport.
Bots (MEASURED split): MAIN-75 = buys of ~0.75 SOL (curve SOL >= 0.62), TIMER6-50 = buys of ~0.5 SOL (curve SOL < 0.62; 86 % sold at exactly
6 slots). Lot view = lots bought in the window followed to their close. Out: DATA/r8.txt"""
import sys, os, pickle, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); F = pickle.load(open(f"{X.D}/fails.pkl", "rb"))["fails"]
R6 = pickle.load(open(f"{X.D}/r6.pkl", "rb"))["D1"]
TX = {r["sig"]: r for r in pickle.load(open(f"{X.D}/tx.pkl", "rb"))}
RP = {r["sig"]: r for r in pickle.load(open(f"{X.D}/rpc_tx.pkl", "rb"))}
bot = lambda l: "TIMER6-50" if l["sol_curve"] < 0.62 else "MAIN-75"
by_buy = {l["buy_sig"]: l for l in L}; by_sell = {l["sells"][0][0]: l for l in L}; fl = {f["sig"]: f for f in F}
lotid = {l["lot_id"]: l for l in L}
C = collections.Counter(); N = collections.Counter()
for sig in R6["rows"]:
    r = TX.get(sig) or RP.get(sig)
    if not r["own"]: continue
    if r["ok"] and r["kind"] == "buy": C[bot(by_buy[sig])] += r["sd"]; N[bot(by_buy[sig]) + " buys"] += 1
    elif r["ok"] and r["kind"] == "sell": C[bot(by_sell[sig])] += r["sd"]; N[bot(by_sell[sig]) + " sells"] += 1
    elif not r["ok"]:
        f = fl.get(sig)
        if f and f["lot_id"] is not None: C[bot(lotid[f["lot_id"]])] += r["sd"]; N[bot(lotid[f["lot_id"]]) + " failed (on a filled position)"] += 1
        else: C["failed attempts, no fill"] += r["sd"]; N["failed attempts, no fill"] += 1
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
tot = sum(C.values())
P(f"24 h window {X.pkt(X.W0)} -> {X.pkt(X.W1)} PKT, cash view")
P("| bot | cash NET SOL |"); P("|---|---|")
for k in ("MAIN-75", "TIMER6-50", "failed attempts, no fill"): P(f"| {k} | {C[k]/1e9:+.9f} |")
P(f"| = sum | {tot/1e9:+.9f} |"); P(f"| reconciled trading NET (r6) | {R6['trading']/1e9:+.9f} |"); P(f"| difference | {tot - R6['trading']} lamports |")
P("counts: " + ", ".join(f"{k} {v}" for k, v in sorted(N.items())))
P("\nlot view (lots bought in the window, followed to close):")
P("| bot | lots | net SOL | mSOL/lot | return on SOL in | win | hold p25/50/75 slots | exits at 3 / 6 / 60-62 slots |"); P("|---|---|---|---|---|---|---|---|")
for b_ in ("MAIN-75", "TIMER6-50"):
    v = [l for l in L if X.W0 <= l["bt"] < X.W1 and bot(l) == b_]
    pn = np.array([l["pnl_cash"] for l in v]); h = np.array([l["hold_slots"] for l in v])
    P(f"| {b_} | {len(v)} | {pn.sum():+.3f} | {1000*pn.mean():+.1f} | {100*pn.sum()/sum(l['cost'] for l in v):+.2f}% | {100*np.mean(pn>0):.0f}% | {X.pct(h,25):.0f}/{X.med(h):.0f}/{X.pct(h,75):.0f} | "
      f"{100*np.mean(h==3):.0f}% / {100*np.mean(h==6):.0f}% / {100*np.mean((h>=60)&(h<=62)):.0f}% |")
P("\nall days (lots by buy day, PKT):")
for d in ("10-25", "10-26", "10-27", "10-28"):
    import time
    row = []
    for b_ in ("MAIN-75", "TIMER6-50"):
        v = [l for l in L if time.strftime("%m-%d", time.gmtime(int(l["bt"]) + 18000)) == d and bot(l) == b_]
        row.append(f"{b_} {len(v)} lots {sum(l['pnl_cash'] for l in v):+.2f}")
    P(f"  {d}: " + " | ".join(row))
open(f"{X.D}/r8.txt", "w").write("\n".join(out) + "\n")

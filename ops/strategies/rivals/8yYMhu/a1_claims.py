#!/usr/bin/env python3
"""8yYMhu a1 (read-only): check the shared analysis' claims with exact numbers from lots.pkl / buys.pkl / fails.pkl.
Out: DATA/a1.txt"""
import sys, os, pickle, collections, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); B = pickle.load(open(f"{X.D}/buys.pkl", "rb")); F = pickle.load(open(f"{X.D}/fails.pkl", "rb"))["fails"]
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
day = lambda t: time.strftime("%m-%d", time.gmtime(int(t) + 18000))
hour = lambda t: int(time.strftime("%H", time.gmtime(int(t) + 18000)))
for l in L:
    l["curve_gross"] = sum(0 for _ in [0])
# curve SOL before pump fees: buy sol_curve, sell curve sol = proceeds + fees (need events) -> recompute from tx.pkl
TX = {r["sig"]: r for r in pickle.load(open(f"{X.D}/tx.pkl", "rb"))}
RP = {r["sig"]: r for r in pickle.load(open(f"{X.D}/rpc_tx.pkl", "rb"))} if os.path.exists(f"{X.D}/rpc_tx.pkl") else {}
nofee = 0
for l in L:
    sig = l["sells"][0][0]; r = TX.get(sig) or RP.get(sig)
    ev = r["events"][0] if r and r["events"] else None
    if ev is None:
        r2 = RP.get(sig); ev = r2["events"][0] if r2 and r2["events"] else None
    if ev: l["sell_curve_sol"] = ev["sol"] / 1e9; l["sell_fees"] = (ev["fee"] + ev["cfee"]) / 1e9
    else: l["sell_curve_sol"] = l["proceeds"]; l["sell_fees"] = 0.0; nofee += 1
    l["gross_curve"] = l["sell_curve_sol"] - l["sol_curve"]           # before pump/creator fees
    l["fees_pump"] = l["pfee"] + l["cfee"] + l["sell_fees"]
    l["costs_tx"] = l["buy_txfee"] + l["buy_tip"] + l["sell_txfee"] + l["sell_tip"] + l["buy_other"] - l["sell_other"] + l["rent_c"] - l["rent_x"]
P(f"lots {len(L)}; sells without a decoded TradeEvent (fees unknown, counted at net) {nofee}")
orph = [f for f in F if f["lot_id"] is None]
P(f"failed txs {len(F)} (attached to a lot {len(F) - len(orph)}, orphan attempts {len(orph)}), fee {sum(f['fee'] for f in F):.6f} SOL")
t0 = min(l["bt"] for l in L); t1 = max(l["bt"] for l in L)
P(f"first buy {X.pkt(t0)} PKT, last buy {X.pkt(t1)} PKT")
def summ(ls, fs, lab):
    g = sum(l["gross_curve"] for l in ls); pf = sum(l["fees_pump"] for l in ls); after = sum(l["gross"] for l in ls)
    tx = sum(l["costs_tx"] for l in ls); ff = sum(f["fee"] for f in fs)
    net = after - tx - ff
    mints = {l["mint"] for l in ls}
    P(f"{lab:26} buys {len(ls):6} tokens {len(mints):5} | curve gross (before pump fees) {g:+9.3f} | pump+creator fees {-pf:+8.3f} | after pump fees {after:+9.3f} "
      f"| tx fees+tips+rent+other {-tx:+7.3f} | failed txs {-ff:+7.3f} ({len(fs)}) | NET {net:+9.3f}")
    return dict(g=g, pf=pf, after=after, tx=tx, ff=ff, net=net, n=len(ls), mints=len(mints))
P("\n== P&L by PKT day (lots by buy time; failed txs by their own time) ==")
res = {}
for d in sorted({day(l["bt"]) for l in L}):
    res[d] = summ([l for l in L if day(l["bt"]) == d], [f for f in F if day(f["bt"]) == d], d)
res["all"] = summ(L, F, "ALL (10-25 11:36 -> 10-29 02:00)")
claimw = (1792909695, 1793214000)       # wallet start -> 10-29 00:00 PKT ("10-25 -> 10-28")
res["claim"] = summ([l for l in L if claimw[0] <= l["bt"] < claimw[1]], [f for f in F if claimw[0] <= f["bt"] < claimw[1]], "claim window 10-25..10-28")
res["24h"] = summ([l for l in L if X.W0 <= l["bt"] < X.W1], [f for f in F if X.W0 <= f["bt"] < X.W1], "24h 10-27 20:00->10-28 20:00")
days = (claimw[1] - claimw[0]) / 86400
P(f"claim window length {days:.2f} days -> curve gross {res['claim']['g'] / days:+.1f}/day, after pump fees {res['claim']['after'] / days:+.1f}/day, NET {res['claim']['net'] / days:+.1f}/day")
P("\n== size ==")
c = np.array([l["cost"] for l in L]); sc = np.array([l["sol_curve"] for l in L])
P(f"SOL spent per buy (incl pump fees) p5/25/50/75/95 = " + "/".join(f"{X.pct(c, q):.4f}" for q in (5, 25, 50, 75, 95)) + f"; curve SOL p50 {X.med(sc):.4f}")
P("most common spend values:", collections.Counter(round(x, 4) for x in c).most_common(8))
for d in sorted({day(l["bt"]) for l in L}):
    v = np.array([l["cost"] for l in L if day(l["bt"]) == d]); P(f"  {d}: n {len(v)} p10/50/90 {X.pct(v,10):.4f}/{X.med(v):.4f}/{X.pct(v,90):.4f}  share within 0.74-0.78: {100*np.mean((v>0.74)&(v<0.78)):.0f}%")
P("\n== same slot as a >=1 SOL sell ==")
Bt = [B[l["lot_id"]] for l in L if B[l["lot_id"]].get("tape") and B[l["lot_id"]].get("me_on_tape")]
n = len(Bt)
a = sum(r["sell1_same_slot_before"] > 0 for r in Bt); b = sum(r["sell1_same_slot_any"] > 0 for r in Bt)
pv = sum(r.get("prev_buy") is False and r.get("prev_sol", 0) >= 1 for r in Bt)
pvs = sum(r.get("prev_buy") is False and r.get("prev_sol", 0) >= 1 and r.get("prev_gap") == 0 for r in Bt)
tg0 = sum(r.get("trig_gap") == 0 for r in Bt); tg1 = sum(r.get("trig_gap") == 1 for r in Bt)
P(f"buys on tape {n}: a >=1 SOL outside sell earlier in HIS slot {a} ({100*a/n:.1f}%); any >=1 SOL sell in his slot {b} ({100*b/n:.1f}%); "
  f"previous outside trade is a >=1 SOL sell {pv} ({100*pv/n:.1f}%), same slot {pvs} ({100*pvs/n:.1f}%); last >=1 SOL sell 0 slots back {tg0} ({100*tg0/n:.1f}%), 1 slot back {tg1} ({100*tg1/n:.1f}%)")
P("\n== hold ==")
h = np.array([l["hold_slots"] for l in L]); hs = np.array([l["hold_s"] for l in L])
P(f"hold slots p10/25/50/75/90 = " + "/".join(f"{X.pct(h, q):.0f}" for q in (10, 25, 50, 75, 90)) + f"; seconds (block clock) p25/50/75 = " + "/".join(f"{X.pct(hs, q):.0f}" for q in (25, 50, 75)))
P(f"  same-slot sells (hold 0) {np.mean(h==0)*100:.1f}%; hold <=2 slots {np.mean(h<=2)*100:.1f}%; >100 slots {np.mean(h>100)*100:.1f}%; max {h.max()}")
P("\n== win rate ==")
lot_net = np.array([l["pnl_cash"] for l in L])
P(f"per lot: win (net incl. attached failed fees) {100*np.mean(lot_net>0):.1f}%; gross-curve win {100*np.mean(np.array([l['gross_curve'] for l in L])>0):.1f}%; after-pump-fee win {100*np.mean(np.array([l['gross'] for l in L])>0):.1f}%; mean net {1000*lot_net.mean():+.2f} mSOL")
tok = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
for l in L:
    t = tok[l["mint"]]; t[0] += l["gross_curve"]; t[1] += l["gross"]; t[2] += l["pnl_cash"]
tv = np.array(list(tok.values()))
P(f"per token ({len(tv)}): win gross-curve {100*np.mean(tv[:,0]>0):.1f}% mean {1000*tv[:,0].mean():+.1f} mSOL | after pump fees win {100*np.mean(tv[:,1]>0):.1f}% mean {1000*tv[:,1].mean():+.1f} | net win {100*np.mean(tv[:,2]>0):.1f}% mean {1000*tv[:,2].mean():+.1f}")
P(f"lots per token: mean {len(L)/len(tv):.2f}; tokens with 1 lot {sum(1 for m in tok if sum(1 for l in L if l['mint']==m)==1) if False else ''}")
P("\n== hourly profile (PKT, all days) ==")
hb = collections.Counter(hour(l["bt"]) for l in L); hp = collections.Counter(); hg = collections.Counter()
for l in L: hp[hour(l["bt"])] += l["pnl_cash"]; hg[hour(l["bt"])] += l["gross_curve"]
for hh in range(24): P(f"  {hh:02d}:00 buys {hb[hh]:5} net {hp[hh]:+7.2f} gross {hg[hh]:+7.2f}")
pickle.dump(dict(res=res), open(f"{X.D}/a1.pkl", "wb"))
open(f"{X.D}/a1.txt", "w").write("\n".join(out) + "\n")

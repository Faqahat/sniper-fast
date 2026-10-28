#!/usr/bin/env python3
"""grad agent, step 5: reproduce E2x1's GRAD lots (sold on PumpSwap) from the tape and check P&L vs lots.pkl.
Per lot: entry vSOL / age / slots before curve completion, completion slot, migration slot, his PumpSwap sell (slot, pool state,
SOL out) from the recorded PumpSwap event; pool-maths check; what the same tokens would give sold at migration + N slots."""
import pickle, hashlib
import numpy as np
from glib import Tape, last_before, pool_state_after, pool_fee, pkt

def sigh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")
T = Tape()
L = pickle.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/lots.pkl", "rb"))
G = sorted([l for l in L if l.get("swap_sell")], key=lambda l: l["s"])
NS = [2, 5, 10, 20, 48, 100, 200]
rows = []
print("day  time(PKT)       mint     bot     cost  vsol_in  age_s  buy->cmp  cmp->mig  mig->sell  last->sell  his_out  pool_math  lots_proc   pnl   | pnl if sold at mig+N: " + " ".join(f"N{n}" for n in NS))
for l in G:
    m = l["mint"]; tr = T.trades(m)
    comp = np.nonzero(tr["rtok"] == 0)[0] if len(tr) else []
    cs = int(tr["slot"][comp[0]]) if len(comp) else None
    last_curve = int(tr["slot"][-1]) if len(tr) else None
    mg = T.mig.get(m)
    sell_sig, sell_slot = l["sells"][0][0], l["sells"][0][1]
    P = T.pool_events(mg["pool"]) if mg else None
    ev = None
    if P is not None and len(P):
        h = sigh(sell_sig); w = np.nonzero(P["sigh"] == h)[0]
        if len(w): ev = P[w[0]]
    his_out = pm = None
    if ev is not None:
        fee = (float(ev["lpfee"]) + float(ev["pfee"]) + float(ev["ccfee"])) / float(ev["quote"])
        his_out = float(ev["uquote"]) / 1e9
        kev = int(w[0]); pb, pq = pool_state_after(P, kev - 1, mg); b = float(ev["base"])
        pm = (pq - pb * pq / (pb + b)) * (1 - fee) / 1e9
    alt = []
    q = float(l["tok"])
    other = l["pnl_cash"] - (l["proceeds"] - l["cost"])          # all non-trade costs as he paid them
    for n in NS:
        if mg is None: alt.append(np.nan); continue
        cm = T.clock(mg["slot"], mg["idx"])
        sx, ix = T.position(cm + n + 0.31)                         # + 66 ms landing
        kk = last_before(P, sx, ix); pb, pq = pool_state_after(P, kk, mg); fee = pool_fee(P, kk)
        out = (pq - pb * pq / (pb + q)) * (1 - fee) / 1e9
        alt.append(out - l["cost"] + other)
    r = dict(day=l["day"], t=pkt(l["bt"]).strftime("%m-%d %H:%M:%S"), mint=m, bot=l["bot"], cost=l["cost"], vsol=l["vsol_after"], age=l["age_s"],
             buy_to_cmp=(cs - l["s"]) if cs else None, cmp_to_mig=(mg["slot"] - cs) if (mg and cs) else None,
             mig_to_sell=(sell_slot - mg["slot"]) if mg else None, last_to_sell=(sell_slot - last_curve) if last_curve else None,
             his_out=his_out, pool_math=pm, proceeds=l["proceeds"], pnl=l["pnl"], alt=alt, sell_sig=sell_sig, buy_sig=l["buy_sig"])
    rows.append(r)
    f = lambda v, p=3: "  -  " if v is None else f"{v:.{p}f}"
    print(f"{r['day']:4} {r['t']} {m[:8]} {r['bot']:6} {r['cost']:.3f} {r['vsol']:6.1f} {r['age']:6} {str(r['buy_to_cmp']):>8} {str(r['cmp_to_mig']):>8} {str(r['mig_to_sell']):>9} {str(r['last_to_sell']):>10}  {f(his_out)}  {f(pm)}  {r['proceeds']:.3f}  {r['pnl']:+.3f} | " + " ".join(f"{a:+.2f}" for a in alt))
pickle.dump(rows, open("/home/moiz/sniper-data/e2x1_dissect/grad/his.pkl", "wb"))
for d in ("D0", "D1"):
    R = [r for r in rows if r["day"] == d]
    if not R: continue
    print(d, "lots", len(R), "his pnl", round(sum(r["pnl"] for r in R), 3), "| at mig+N:", " ".join(f"N{n}={np.nansum([r['alt'][k] for r in R]):+.2f}" for k, n in enumerate(NS)))

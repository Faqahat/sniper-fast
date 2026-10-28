#!/usr/bin/env python3
"""8yYMhu x1 (read-only): example trades with GMGN token links and solscan tx links for every claim. Out: DATA/x1.txt"""
import sys, os, pickle, collections, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); B = pickle.load(open(f"{X.D}/buys.pkl", "rb")); A = pickle.load(open(f"{X.D}/att.pkl", "rb"))
EP = {e["lot"]: e for e in pickle.load(open(f"{X.D}/exitpath.pkl", "rb"))}
H = pickle.load(open(f"{X.D}/h2h.pkl", "rb")); a5 = pickle.load(open(f"{X.D}/a5.pkl", "rb"))
import tlib as T
random.seed(29)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
D1 = [l for l in L if X.W0 <= l["bt"] < X.W1]
def lk(l): return f"[{l['mint'][:8]}]({X.gm(l['mint'])}) buy [{l['buy_sig'][:8]}]({X.ss(l['buy_sig'])}) sell [{l['sells'][0][0][:8]}]({X.ss(l['sells'][0][0])})"
P("## A. P&L examples (24 h window), net SOL incl. fees/tips/failed copies")
s = sorted(D1, key=lambda l: l["pnl_cash"])
for l in s[-4:][::-1] + s[:3] + random.sample(D1, 3):
    P(f"- {lk(l)} {X.pkt(l['bt'])} cost {l['cost']:.4f} net {l['pnl_cash']:+.4f} hold {l['hold_slots']} slots")
P("\n## B. same-slot trigger: >=1 SOL sell -> his buy (index gap, chain-clock ms, leader)")
tr_ = [l for l in D1 if B.get(l["lot_id"], {}).get("trig_gap") == 0]
for l in random.sample(tr_, 7):
    b = B[l["lot_id"]]
    tsig = None
    tr = T.trades(l["mint"])
    P(f"- {lk(l)} trigger {b['trig_sol']:.2f} SOL sell by {b['trig_user'][:8]} at idx {b['trig_idx']} -> his buy idx {l['i']} (gap {b['trig_igap']} txs, {b['ms']:.0f} ms), leader {b['client']}/{b['area']}, net {l['pnl_cash']:+.4f}")
P("\n## C. exits: slot-3, slot-6, timeout (61 slots)")
for lab, cond in (("slot 3", lambda e: e["hold"] == 3), ("slot 6", lambda e: e["hold"] == 6), ("timeout 61", lambda e: e["hold"] == 61), ("winner held 20-40", lambda e: 20 <= e["hold"] <= 40 and e["pnl"] > 0.05)):
    v = [l for l in D1 if l["lot_id"] in EP and cond(EP[l["lot_id"]])]
    for l in random.sample(v, min(5, len(v))):
        e = EP[l["lot_id"]]
        P(f"- [{lab}] {lk(l)} ret at exit {100*e['ret_exit']:+.1f}% max during hold {100*e['ret_max']:+.1f}% net {l['pnl_cash']:+.4f}")
P("\n## D. failed attempts (on chain): late (6001) / band (6401) / slippage (6002) / duplicate account (0)")
for o in ("late", "band", "slip", "dup"):
    v = [a for a in A if a["out"] == o and X.W0 <= a["bt"] < X.W1 and "trig_slot" in a]
    for a in random.sample(v, min(5, len(v))):
        P(f"- [{o}] [{a['mint'][:8]}]({X.gm(a['mint'])}) [{a['sig'][:8]}]({X.ss(a['sig'])}) slot {a['s']} idx {a['i']}, trigger slot {a['trig_slot']} idx {a['trig_idx']} ({a['trig_sol']:.2f} SOL), trig position {a['trig_frac']:.2f} of block")
P("\n## E. RPC-decoded guards (deadline = trigger slot; band around the post-sell vSOL)")
v = [r for r in a5 if r.get("trig_slot") and r["dl"] == r.get("trig_slot") and r["lo"]]
for r in random.sample(v, 6):
    P(f"- [{r['sig'][:8]}]({X.ss(r['sig'])}) {'LANDED' if r['ok'] else 'failed ' + r['err']} slot {r['slot']} deadline {r['dl']} (trigger slot {r['trig_slot']}); band vSOL {r['lo']:.3f}..{r['hi']:.3f} vs post-sell {r['trig_vsol']:.3f}; BuyV3 max SOL {r['max_sol']:.4f}; tips {[(t[2], t[1]) for t in r['tips']]}")
P("\n## F. head-to-head on the same dump (our pre-send fill vs his buy)")
same = [h for h in H if h.get("his_lot") is not None and h.get("his_trig") == (h.get("dump_slot"), h.get("dump_idx"))]
for h in random.sample(same, min(7, len(same))):
    l = L[h["his_lot"]]
    P(f"- [{h['mint'][:8]}]({X.gm(h['mint'])}) dump {h['dump_sol']:.2f} SOL; OUR fill [{h['buy_sig'][:8]}]({X.ss(h['buy_sig'])}) slot {h['s']} idx {h['i']} ({h['run']}, {h['cost']:.3f} SOL, realized {h['pnl']:+.4f}); "
      f"HIS buy [{l['buy_sig'][:8]}]({X.ss(l['buy_sig'])}) slot {l['s']} idx {l['i']} ({l['cost']:.3f} SOL, net {l['pnl_cash']:+.4f}, hold {l['hold_slots']} slots) -> {'HE' if h['his_first'] else 'WE'} landed first; ours re-priced at his exit {h.get('rep_hisexit', float('nan')):+.4f}")
P("\n## G. size examples (0.75 and 0.5 targets)")
for tgt in (0.7594, 0.5062):
    v = [l for l in D1 if abs(l["cost"] - tgt) < 0.0001]
    for l in random.sample(v, min(3, len(v))): P(f"- spend {l['cost']:.4f}: {lk(l)}")
open(f"{X.D}/x1.txt", "w").write("\n".join(out) + "\n")

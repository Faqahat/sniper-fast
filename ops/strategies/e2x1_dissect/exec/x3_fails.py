#!/usr/bin/env python3
"""Q2 failed duplicates (MEASURED, recorder tx.pkl + recon fails.pkl). Which copy (relay:tip) fails, error codes, cost per lot,
landed-vs-failed copy pairs, slot gap between the landed copy and the failed copy. Also: which copy lands, by leader client.
Out: sniper-data/e2x1_dissect/exec/x3.txt"""
import sys, collections, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
TX = pickle.load(open(f"{X.R}/tx.pkl", "rb")); F = pickle.load(open(f"{X.R}/fails.pkl", "rb"))
L = {l["lot_id"]: l for l in X.lots()}
txs = {t["sig"]: t for t in TX}
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
def day(bt): return "D1" if X.D1[0] <= bt < X.D1[1] else ("D0" if X.D0[0] <= bt < X.D0[1] else "x")
def copy(t):
    if t is None: return "?"
    return f"{t.get('relay')}:{sum(t.get('tip_amt') or [0])}"
for D in ("D1", "D0"):
    fl = [f for f in F["fails"] if day(f["bt"]) == D]
    P(f"===== {D}: failed txs {len(fl)}, fee total {sum(f['fee'] for f in fl):.6f} SOL")
    c = collections.Counter((f["fkind"], copy(txs.get(f["sig"])), f["err"].replace("'InstructionError': ", "")[:60]) for f in fl)
    for k, v in c.most_common(20): P(f"  {v:5}  {k}")
    lots = [l for l in X.lots() if l["day"] == D]
    nf = sum(l["n_fail"] for l in lots); P(f"  lots {len(lots)}; failed attached to lots {nf}; fail fee/lot {1000*sum(l['fail_fee'] for l in lots)/len(lots):.3f} mSOL; lots with >=1 failed {sum(l['n_fail']>0 for l in lots)}")
    # pairs: landed buy copy vs failed buy copy on the same lot; landed sell copy vs failed sell copy
    pb = collections.Counter(); ps = collections.Counter(); gb = []; gs = []
    for f in fl:
        l = L.get(f["lot_id"]); t = txs.get(f["sig"])
        if l is None: continue
        if f["fkind"] == "buy":
            pb[(f"landed {l['buy_relay']}:{l['buy_tip_amt']}", f"failed {copy(t)}")] += 1; gb.append(f["s"] - l["s"])
        else:
            if l["sells"]:
                last = l["sells"][-1]; lt = txs.get(last[0])
                ps[(f"landed {copy(lt)}", f"failed {copy(t)}")] += 1; gs.append(f["s"] - last[1])
    P("  buy pairs:"); [P(f"    {v:5} {k}") for k, v in pb.most_common(8)]
    P(f"    failed-buy slot - landed-buy slot: " + str(collections.Counter(gb).most_common(6)))
    P("  sell pairs:"); [P(f"    {v:5} {k}") for k, v in ps.most_common(8)]
    P(f"    failed-sell slot - closing-sell slot: " + str(collections.Counter(gs).most_common(8)))
    # landed copy share by leader client (buys and sells)
    cc = collections.defaultdict(collections.Counter)
    for l in lots:
        cc[X.leader(l["s"])[1]][f"{l['buy_relay']}:{l['buy_tip_amt']}"] += 1
    P("  landed BUY copy by leader client:")
    for k, v in sorted(cc.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(v.values()); P(f"    {k:18} n={n:4} " + "  ".join(f"{a} {100*b/n:3.0f}%" for a, b in v.most_common()))
    cs = collections.defaultdict(collections.Counter)
    for l in lots:
        for s in l["sells"]:
            t = txs.get(s[0]); cs[X.leader(s[1])[1]][copy(t)] += 1
    P("  landed SELL copy by leader client:")
    for k, v in sorted(cs.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(v.values()); P(f"    {k:18} n={n:4} " + "  ".join(f"{a} {100*b/n:3.0f}%" for a, b in v.most_common(4)))
# examples D1
P("examples (D1 failed copies):")
ex = collections.defaultdict(list)
for f in F["fails"]:
    if day(f["bt"]) != "D1" or f["lot_id"] is None: continue
    k = (f["fkind"], f["err"][-14:]); 
    if len(ex[k]) < 5: ex[k].append(f)
for k, v in ex.items():
    for f in v:
        l = L[f["lot_id"]]; P(f"  {k[0]} {f['err'][-20:]} copy={copy(txs.get(f['sig']))} token {X.gm(f['mint'])} failed {X.ss(f['sig'])} landed-buy {l['buy_tx']}")
open(f"{X.X}/x3.txt", "w").write("\n".join(out) + "\n")

#!/usr/bin/env python3
"""8yYMhu o2 (read-only): head-to-head with OUR live pre-send fills (ours.pkl) and re-pricing of our fills at later exits.
For each of our fills: the dump we bought (last outside sell >= 0.3 SOL within 3 slots before our buy), whether 8yYMhu bought the same
dump (a lot of his on the mint whose buy is within +-3 slots of ours), block order (who landed first), each side's P&L, and
OUR tokens re-priced on the curve at end of slot buy+{1,2,5,9,31} and just before HIS sell (curve path with our own sell added back,
constant product; 1.25 % pump+creator fee on the sell). Out: DATA/h2h.pkl, DATA/o2.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
uidm = T.uid(); oid = {uidm[u] for u in OURS if u in uidm}; wid = uidm[X.W]; users = T.names()[1]
R = pickle.load(open(f"{X.D}/ours.pkl", "rb")); L = pickle.load(open(f"{X.D}/lots.pkl", "rb"))
lots_m = collections.defaultdict(list)
for l in L: lots_m[l["mint"]].append(l)
FEE = 0.0125; EXS = (1, 2, 5, 9, 31)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
H = []
for r in R:
    tr = T.trades(r["mint"])
    h = dict(r)
    if tr is None: H.append(h); continue
    key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64)
    kb = r["s"] * 4096 + r["i"]; p = int(np.searchsorted(key, kb))
    if not (p < len(tr) and key[p] == kb): H.append(h); continue
    h["tape"] = True
    b = tr[:p]
    sel = np.nonzero(~np.isin(b["user"], list(oid)) & (b["buy"] == 0) & (b["sol"] >= 300_000_000) & (b["slot"] >= r["s"] - 3))[0]
    if len(sel):
        t = b[sel[-1]]; h.update(dump_slot=int(t["slot"]), dump_idx=int(t["idx"]), dump_sol=int(t["sol"]) / 1e9, dump_user=users[t["user"]],
                                  our_igap=(r["i"] - int(t["idx"])) if int(t["slot"]) == r["s"] else None, our_gap=r["s"] - int(t["slot"]))
    # our sell in tape (to add it back)
    vs = tr["vsol"].astype(np.float64); vt = tr["vtok"].astype(np.float64); kk = vs * vt
    ours_sell = np.nonzero(np.isin(tr["user"], list(oid)) & (tr["buy"] == 0) & (key > kb))[0]
    addback = np.zeros(len(tr))
    if len(ours_sell):
        q = ours_sell[0]; addback[q:] = float(tr["sol"][q]); h["our_sell_tape"] = (int(tr["slot"][q]), int(tr["idx"][q]))
    Vh = vs + addback
    tok = float(r["tokens"]); kq = kk[p]
    def sell_value(j):
        V = Vh[j]; T1 = kq / V
        return (kq / (T1 - 0) - kq / (T1 + tok)) * 0 + (V - kq / (T1 + tok))
    for x in EXS:
        j = int(np.searchsorted(tr["slot"], r["s"] + x, side="right")) - 1
        h[f"rep_{x}"] = (sell_value(max(j, p)) * (1 - FEE)) / 1e9 - r["cost"]
    if len(ours_sell):
        h["rep_ourexit_paper"] = (sell_value(ours_sell[0] - 1) * (1 - FEE)) / 1e9 - r["cost"]
    h["real_curve_net"] = (r["sol_out"] * (1 - FEE) - r["cost"]) if r["sol_out"] else None
    # his lot on the same dump
    best = None
    for l in lots_m.get(r["mint"], []):
        if abs(l["s"] - r["s"]) <= 3 and (best is None or abs(l["s"] - r["s"]) < abs(best["s"] - r["s"])): best = l
    if best is not None:
        h.update(his_lot=best["lot_id"], his_s=best["s"], his_i=best["i"], his_pnl=best["pnl_cash"], his_gross=best["gross"], his_cost=best["cost"],
                 his_hold=best["hold_slots"], his_close=(best["close_s"], best["close_i"]), his_first=(best["s"], best["i"]) < (r["s"], r["i"]),
                 his_buy_sig=best["buy_sig"], his_sell_sig=best["sells"][0][0])
        # re-price ours just before his sell
        kc = best["close_s"] * 4096 + best["close_i"]; jc = int(np.searchsorted(key, kc)) - 1
        if jc >= p: h["rep_hisexit"] = (sell_value(jc) * (1 - FEE)) / 1e9 - r["cost"]
        # same trigger? his trigger (last >=1 SOL outside sell before his buy)
        kh = best["s"] * 4096 + best["i"]; ph = int(np.searchsorted(key, kh)); bh = tr[:ph]
        sh = np.nonzero((bh["user"] != wid) & ~np.isin(bh["user"], list(oid)) & (bh["buy"] == 0) & (bh["sol"] >= 1_000_000_000))[0]
        if len(sh): h["his_trig"] = (int(bh["slot"][sh[-1]]), int(bh["idx"][sh[-1]]))
    H.append(h)
pickle.dump(H, open(f"{X.D}/h2h.pkl", "wb"))
T_ = [h for h in H if h.get("tape")]
P(f"our fills {len(H)}; on tape {len(T_)}")
both = [h for h in T_ if "his_lot" in h]
same = [h for h in both if h.get("his_trig") == (h.get("dump_slot"), h.get("dump_idx"))]
P(f"his lot within +-3 slots on the same mint: {len(both)}; same dump (his trigger == our dump): {len(same)}")
if same:
    hf = sum(h["his_first"] for h in same)
    P(f"  same dump: HE landed first {hf}, WE landed first {len(same)-hf}")
    ours_real = np.array([h["pnl"] or 0 for h in same]); his = np.array([h["his_pnl"] for h in same])
    P(f"  same dump P&L: ours realized {ours_real.sum():+.4f} SOL ({1000*ours_real.mean():+.2f} mSOL/fill, size p50 {X.med([h['cost'] for h in same]):.3f}); "
      f"his net {his.sum():+.4f} ({1000*his.mean():+.2f} mSOL/lot, size p50 {X.med([h['his_cost'] for h in same]):.3f}); his hold p50 {X.med([h['his_hold'] for h in same]):.0f} slots")
    for k in ["real_curve_net", "rep_ourexit_paper"] + [f"rep_{x}" for x in EXS] + ["rep_hisexit"]:
        v = np.array([h[k] for h in same if h.get(k) is not None])
        P(f"    ours on same dumps, {k:18}: n {len(v):3} sum {v.sum():+.4f} mean {1000*v.mean():+.2f} mSOL")
P("ALL our fills on tape, our tokens re-priced (curve result after pump fees, before tx fees/tips; size p50 %.3f):" % X.med([h["cost"] for h in T_]))
for k in ["real_curve_net", "rep_ourexit_paper"] + [f"rep_{x}" for x in EXS]:
    v = np.array([h[k] for h in T_ if h.get(k) is not None])
    P(f"  {k:18}: n {len(v):3} sum {v.sum():+.4f} mean {1000*v.mean():+.2f} mSOL  win {100*np.mean(v>0):.0f}%")
for run in sorted({h["run"] for h in T_}):
    v = [h for h in T_ if h["run"] == run]
    P(f"  {run}: n {len(v)} real {sum(h['real_curve_net'] or 0 for h in v):+.4f} | " + " ".join(f"+{x}:{sum(h[f'rep_{x}'] for h in v):+.3f}" for x in EXS))
open(f"{X.D}/o2.txt", "w").write("\n".join(out) + "\n")

#!/usr/bin/env python3
"""TIMING step 6: DIRECT scoring (all 20 live runs) of rules a (stop tries at signing), b (whale-wait), d (skip at arm) -- PREREG.txt.
gain = - realized P&L@0.696 of every live fill the rule blocks (winners and losers).  Out: direct.json + printed tables."""
import sys, pickle, json, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/timing")
import tlib as T
D = "/home/it/sniper-data/prevent/timing"
FC = pickle.load(open(f"{D}/fillctx.pkl", "rb"))
G = {(f["run"], f["ses"], f["kind"], f["w"]): f for f in pickle.load(open("/home/it/sniper-data/prevent/guards/fills.pkl", "rb"))}
SUP = 1e15
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]


def flag_a(f, X, tau, only_whale=False):
    S = f["sign_slot"] or f["slot"]
    Hs = f["Hs"] if f["Hs"] is not None else {}
    trig_bal = G[(f["run"], f["ses"], f["kind"], f["w"])].get("trig_bal") or 0
    for w, (bal, first, cost) in Hs.items():
        if bal < X / 100 * SUP or first is None: continue
        if only_whale:
            if f["kind"] != "t2" or w != f["whale"] or bal < 0.5 * trig_bal: continue
        p, n = T.hz(w, S, f["mint"], S - first, 3)
        if p is not None and p >= tau: return True, w
    return False, None


def flag_d(f, tau):
    if f["kind"] != "t2" or not f["Ht"]: return False, None
    S = f["trig_slot"]
    for w, (bal, first, cost) in f["Ht"].items():
        if w == f["whale"] or bal < 0.06 * SUP or first is None: continue
        p, n = T.hz(w, S, f["mint"], S - first, 12)
        if p is not None and p >= tau: return True, w
    return False, None


V = {}
for X in (3, 6):
    for tau in (0.2, 0.3, 0.5): V[f"a_X{X}_t{tau}"] = (lambda f, X=X, tau=tau: flag_a(f, X, tau))
for tau in (0.2, 0.3, 0.5): V[f"b_whale_t{tau}"] = (lambda f, tau=tau: flag_a(f, 6, tau, only_whale=True))
for tau in (0.3, 0.5): V[f"d_arm6_t{tau}"] = (lambda f, tau=tau: flag_d(f, tau))
res = {}; flags = {}
print(f"{'variant':16s} | {'PICK':>7s} {'r37':>7s} {'r38':>7s} | runs+/- | {'CI90 PICK+TEST':>16s} | {'w/o1':>6s} {'w/o5':>6s} | blk P/T/38 | win/los skipped | verdict")
for name, fn in V.items():
    rows = []; fl = {}
    for f in FC:
        b, w = fn(f)
        p = f["p696"] or 0.0
        rows.append(dict(run=f["run"], t=f["t"], gain=-p if b else 0.0, blocked=b, p696=p))
        fl[(f["run"], f["ses"], f["kind"], f["w"])] = (b, w)
    s = T.score(rows); s["verdict"] = T.verdict(s); res[name] = s; flags[name] = fl
    print(f"{name:16s} | {s['pick']:+7.3f} {s['test']:+7.3f} {s['r38']:+7.3f} | {s['runs_up']:2d}/{s['runs_dn']:2d}   | [{s['ci'][0]:+6.2f},{s['ci'][1]:+6.2f}] | {s['wo1']:+6.2f} {s['wo5']:+6.2f} | "
          f"{s['n_blk_pick']:4d}/{s['n_blk_test']:3d}/{s['n_blk_r38']:3d} | {s['win_sk']:6.2f}/{s['los_sk']:6.2f} | {s['verdict']}")
json.dump(res, open(f"{D}/direct.json", "w"), indent=1)
pickle.dump(flags, open(f"{D}/direct_flags.pkl", "wb"))
print("\nper run (gain @0.696):")
print("run  " + " ".join(f"{k[:12]:>12s}" for k in V))
for r in ORDER: print(f"{r:4s} " + " ".join(f"{res[k]['per'].get(r, 0):+12.3f}" for k in V))

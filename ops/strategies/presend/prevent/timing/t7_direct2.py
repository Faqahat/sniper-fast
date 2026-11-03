#!/usr/bin/env python3
"""TIMING step 7 (ADDED after a/b failed -- post-hoc variants, counted): LANDING-CONDITIONED timer guard.
a2: a try fills only if no 'predicted seller' still holds at its landing.  Predicted seller = a wallet holding >= X% at the try's SIGNING
    slot with timer hazard hz(3) >= tau (online, at signing).  On-chain = a Lighthouse token-account assertion (balance < X%) on each
    predicted seller (<= 6 fit, GUARDS).  OPEN = accounts never closed; NAIVE = a predicted seller that sold out between signing and
    landing closed its account with p 0.39 (GUARDS MEASURED) -> the assertion fails -> the try fails too (expected value).
b2: same, only the T2 whale (holds >= 50% of its trigger balance at landing).
gain = - realized P&L@0.696 of the blocked live fills (expected value for NAIVE).  Out: direct2.json"""
import sys, pickle, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/timing")
import tlib as T
D = "/home/moiz/sniper-data/prevent/timing"
FC = pickle.load(open(f"{D}/fillctx.pkl", "rb"))
G = {(f["run"], f["ses"], f["kind"], f["w"]): f for f in pickle.load(open("/home/moiz/sniper-data/prevent/guards/fills.pkl", "rb"))}
SUP = 1e15; PCLOSE = 0.39
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]


def flags(f, X, tau, whale_only=False):
    """-> (p_block, wallets): p_block = 1 if a predicted seller still holds at landing; else PCLOSE if one sold out before landing (NAIVE)"""
    S = f["sign_slot"] or f["slot"]; Hs = f["Hs"] or {}
    trig_bal = G[(f["run"], f["ses"], f["kind"], f["w"])].get("trig_bal") or 0
    hit = []; gone = []
    for w, (bal, first, cost) in Hs.items():
        if bal < X / 100 * SUP or first is None: continue
        if whale_only and (f["kind"] != "t2" or w != f["whale"]): continue
        p, n = T.hz(w, S, f["mint"], S - first, 3)
        if p is None or p < tau: continue
        bl = f["H"].get(w, {}).get("bal", 0)          # balance just before our buy landed (>= 2% kept in H)
        thr = 0.5 * trig_bal if whale_only else X / 100 * SUP
        if bl >= thr: hit.append(w)
        elif bl <= 0.0005 * SUP: gone.append(w)
    return hit, gone


V = {}
for X in (3, 6):
    for tau in (0.2, 0.3, 0.5): V[f"a2_X{X}_t{tau}"] = dict(X=X, tau=tau, wo=False)
for tau in (0.2, 0.3, 0.5): V[f"b2_whale_t{tau}"] = dict(X=6, tau=tau, wo=True)
res = {}; FL = {}
print(f"{'variant':22s} | {'PICK':>7s} {'r37':>7s} {'r38':>7s} | runs+/- | {'CI90 PICK+TEST':>16s} | {'w/o1':>6s} {'w/o5':>6s} | blk P/T/38 | win/los skipped | verdict")
for name, c in V.items():
    for trt in ("open", "naive"):
        rows = []; fl = {}
        for f in FC:
            hit, gone = flags(f, c["X"], c["tau"], c["wo"])
            pb = 1.0 if hit else (PCLOSE if (trt == "naive" and gone) else 0.0)
            p = f["p696"] or 0.0
            rows.append(dict(run=f["run"], t=f["t"], gain=-p * pb, blocked=pb > 0, p696=p * pb if pb > 0 else p))
            fl[(f["run"], f["ses"], f["kind"], f["w"])] = (pb, hit, gone)
        s = T.score(rows); s["verdict"] = T.verdict(s); res[f"{name}_{trt}"] = s; FL[f"{name}_{trt}"] = fl
        print(f"{name+'_'+trt:22s} | {s['pick']:+7.3f} {s['test']:+7.3f} {s['r38']:+7.3f} | {s['runs_up']:2d}/{s['runs_dn']:2d}   | [{s['ci'][0]:+6.2f},{s['ci'][1]:+6.2f}] | "
              f"{s['wo1']:+6.2f} {s['wo5']:+6.2f} | {s['n_blk_pick']:4d}/{s['n_blk_test']:3d}/{s['n_blk_r38']:3d} | {s['win_sk']:6.2f}/{s['los_sk']:6.2f} | {s['verdict']}")
json.dump(res, open(f"{D}/direct2.json", "w"), indent=1)
pickle.dump(FL, open(f"{D}/direct2_flags.pkl", "wb"))
ks = [k for k in res if k.endswith("open")]
print("\nper run (gain @0.696), OPEN:")
print("run  " + " ".join(f"{k[:14]:>14s}" for k in ks))
for r in ORDER: print(f"{r:4s} " + " ".join(f"{res[k]['per'].get(r, 0):+14.3f}" for k in ks))

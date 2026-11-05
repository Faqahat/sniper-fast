#!/usr/bin/env python3
"""NEWSTRAT TIMED-SELLER pre-send (idea 3): some bots hold for an almost FIXED number of slots (e.g. 8yYMhu TIMER6 sells
6 slots after its buy; 9pQQ's time cap).  Their sell is then predictable to the slot from their visible buy, so we can have a
pre-signed dip buy in flight when it lands (like our T2 engine on whale dumps) and catch the dip bots' bounce.
step A (per run): positions of every wallet with >= 30 closed curve positions: hold slots (first buy -> full exit) and exit SOL.
  -> OUT/n11_hold_<run>.npz
step B (score): timed wallets chosen on FIT days only: >= 30 positions on every fit day, the modal hold h0 (slots) is the same on
  every fit day and >= 50 % of holds are in [h0-1, h0+1] on every fit day, median exit >= 0.4 SOL.
  ARM at its buy slot + h0 - 1 (if still holding), pre-send stream until slot + h0 + 3, limit = price at arm x m (.98/.96/.94);
  fill model, fees and exits as n9_presend.py.  Reactive comparison: land 70 ms after the crossing trade.
usage: n11_timed.py hold RUN... | n11_timed.py score RUN..."""
import sys, json, random
import numpy as np
import nlib as L
from n9_presend import presend_fill, reactive_fill, FAILFEE
import os
MLTS = tuple(float(x) for x in os.environ.get("MLTS", "0.98,0.96,0.94").split(","))

def holds(run):
    t = L.load(run)
    o = np.lexsort((t.cc, t.m, t.u))
    u, m, tk, s, sol = t.u[o], t.m[o], t.tok[o], t.s[o], t.sol[o]
    nsell = np.bincount(t.u[t.tok < 0], minlength=len(t.users))
    sel = nsell[u] >= 30
    U, M_, S0, S1, B0, X = [], [], [], [], [], []
    ul, ml, tl, sl, so, ol = u[sel].tolist(), m[sel].tolist(), tk[sel].tolist(), s[sel].tolist(), sol[sel].tolist(), o[sel].tolist()
    cu, cm, bal, peak, s0, b0 = -1, -1, 0, 0, None, None
    for k in range(len(ul)):
        if ul[k] != cu or ml[k] != cm:
            cu, cm, bal, peak, s0 = ul[k], ml[k], 0, 0, None
        if s0 is None:
            if tl[k] <= 0: continue
            s0, b0 = sl[k], ol[k]; bal = 0; peak = 0
        bal += tl[k]; peak = max(peak, bal)
        if tl[k] < 0 and bal <= 0.005 * peak:
            U.append(cu); M_.append(cm); S0.append(s0); S1.append(sl[k]); B0.append(b0); X.append(so[k]); s0 = None
    np.savez(f"{L.OUT}/n11_hold_{run}.npz", u=t.users[np.array(U)], m=t.mints[np.array(M_)], s0=np.array(S0), s1=np.array(S1),
             xsol=np.array(X), hours=np.array([L.hours(t)]))
    print(run, "positions", len(U), flush=True)

def timed_wallets(fit):
    per = []
    for r in fit:
        z = np.load(f"{L.OUT}/n11_hold_{r}.npz")
        h = z["s1"] - z["s0"]; uu, inv = np.unique(z["u"], return_inverse=True)
        d = {}
        for j in np.nonzero(np.bincount(inv) >= 30)[0]:
            hh = h[inv == j]; xs = z["xsol"][inv == j]
            vals, cnt = np.unique(hh, return_counts=True); h0 = int(vals[np.argmax(cnt)])
            share = float(((hh >= h0 - 1) & (hh <= h0 + 1)).mean())
            d[uu[j]] = (h0, share, float(np.median(xs)) / 1e9)
        per.append(d)
    out = {}
    for w in set.intersection(*[set(p) for p in per]):
        h0s = [p[w][0] for p in per]
        if len(set(h0s)) == 1 and all(p[w][1] >= 0.5 for p in per) and np.median([p[w][2] for p in per]) >= 0.4 and h0s[0] >= 2:
            out[w] = h0s[0]
    return out

def score(run, tw):
    t = L.load(run); la = L.launches(run); rng = random.Random(11)
    tid = {t.uix[w]: h for w, h in tw.items() if w in t.uix}
    rows = np.nonzero(np.isin(t.u, list(tid)) & (t.tok > 0))[0]
    by = {}
    for r in rows:
        mm = str(t.mints[t.m[r]]); lv = la.get(mm)
        if lv is None or lv["may"]: continue
        by.setdefault(int(t.m[r]), []).append(r)
    R = {}
    for mi, rr in by.items():
        M = L.Mint(t, mi)
        for r in rr:
            uid = int(t.u[r]); h0 = tid[uid]
            arm_slot = int(t.s[r]) + h0 - 1
            arm = arm_slot * L.SMS
            # still holding at arm? (its own rows on this mint between its buy and arm)
            own = (M.U == uid) & (M.CC > t.cc[r]) & (M.CC < arm) & (M.TK < 0)
            if own.any(): continue
            t_end = (arm_slot + 5) * L.SMS
            p_a = L.price(float(M.cbal(int(M.idx(arm)))))
            for mlt in MLTS:
                tau, ntry = presend_fill(M, arm, t_end, p_a * mlt, rng)
                fee = ntry * FAILFEE
                for ex, H in (("H200", 200), ("S2", 2 * L.SMS), ("S6", 6 * L.SMS), ("S12", 12 * L.SMS)):
                    if tau is None: R.setdefault((mlt, "ps", ex), []).append((0, -fee, -fee)); continue
                    R.setdefault((mlt, "ps", ex), []).append((1, L.trip(M, [tau], [tau + H])[0] - fee, L.trip(M, [tau], [tau + H], fol=L.FOLSHARE)[0] - fee))
                tr = reactive_fill(M, arm, t_end, p_a * mlt)
                for ex, H in (("H200", 200), ("S2", 2 * L.SMS)):
                    if tr is None: R.setdefault((mlt, "react70", ex), []).append((0, 0.0, 0.0)); continue
                    R.setdefault((mlt, "react70", ex), []).append((1, L.trip(M, [tr], [tr + H])[0], L.trip(M, [tr], [tr + H], fol=L.FOLSHARE)[0]))
    hrs = L.hours(t); out = []
    for k, vals in sorted(R.items()):
        a = np.array(vals); s = L.stats(a[:, 1]); sf = L.stats(a[a[:, 0] == 1, 1])
        out.append(dict(m=k[0], mode=k[1], exit=k[2], windows=len(a), fills=int(a[:, 0].sum()), per_day=round(s["net"] / hrs * 24, 2),
                        mSOL_fill=sf["per"], win=sf["win"], wo5_day=round(s["wo5"] / hrs * 24, 2), f20_day=round(a[:, 2].sum() / 1e9 / hrs * 24, 2)))
    return out

if __name__ == "__main__":
    if sys.argv[1] == "hold":
        for r in sys.argv[2:]: holds(r)
    else:
        tw = timed_wallets(L.RUNS[:3])
        print("timed wallets", len(tw), sorted(tw.items(), key=lambda x: x[1])[:30], flush=True)
        json.dump(tw, open(f"{L.OUT}/n11_timed_wallets.json", "w"))
        for r in sys.argv[2:]:
            o = score(r, tw); json.dump(o, open(f"{L.OUT}/n11_{os.environ.get("TAG","a")}_{r}.json", "w"))
            for x in o: print(L.DAY[r], x)

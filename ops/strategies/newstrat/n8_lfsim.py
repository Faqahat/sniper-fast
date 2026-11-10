#!/usr/bin/env python3
"""NEWSTRAT LEADFOL re-simulation on the tape (independent of n4's stored outcomes) with execution variants:
  guard g: our buy carries a max price = leader's post-buy price x (1+g); if the price at our landing is higher the tx fails (no trade,
           ~7.3k lamports fee).  g in {none, 0.05, 0.10, 0.20}
  exits: fixed K slots after entry (10/25/50), trailing 10 % from peak (reactive +D, cap 25 slots), 'first outside sell >= 0.3 SOL
         after entry' + D (cap 25 slots)
  followers: who buys inside our hold (wallet classes by trade count on the run: BOT>=300, MID 30-299, RET<30; leader itself)
usage: n8_lfsim.py LEADERS_JSON RUN K_SEL [D]   (leader list from an n7 output file)"""
import sys, json
import numpy as np
import nlib as L
import xlib as X
from n5_scan import ev, one_pos

def main(lj, run, K, D=70):
    lead = json.load(open(lj))["leaders"]
    t = L.load(run); la = L.launches(run)
    ntr = np.bincount(t.u, minlength=len(t.users))
    cls = np.where(ntr >= 300, 0, np.where(ntr >= 30, 1, 2))
    lid = set(t.uix[u] for u in lead if u in t.uix)
    t0 = float(t.cc.min()) + 2 * 3600e3
    # leader buy rows
    rows = np.nonzero(np.isin(t.u, list(lid)) & (t.tok > 0) & (-t.sol >= 0.05e9) & (t.fl & 1 == 1))[0]
    by = {}
    for r in rows:
        m = str(t.mints[t.m[r]]); lv = la.get(m)
        if lv is None or lv["may"] or t.cc[r] < t0: continue
        by.setdefault(int(t.m[r]), []).append(r)
    G = [None, 0.05, 0.10, 0.20]
    EX = ["fix10", "fix25", "fix50", "trail10_c25", "sell03_c25"]
    res = {(g, e): [] for g in G for e in EX}
    fails = {g: 0 for g in G}
    fol = np.zeros(4); foln = 0
    for mi, rr in by.items():
        M = L.Mint(t, mi)
        rr = sorted(rr, key=lambda r: t.cc[r])
        lend = -1.0
        for r in rr:
            tc = float(t.cc[r])
            if tc + D < lend: continue
            lend = tc + D + K * L.SMS
            t_in = tc + D
            e, tok = X.entry(M, t_in)
            p_lead = L.price(float(t.cpost[r])); p_in = L.price(float(M.cbal(e)))
            jump = p_in / p_lead - 1
            outs = {"fix10": t_in + 10 * L.SMS, "fix25": t_in + 25 * L.SMS, "fix50": t_in + 50 * L.SMS,
                    "trail10_c25": X.ex_trail(M, t_in, e, tok, 0.10, D, 25 * L.SMS)[0]}
            x25 = int(M.idx(t_in + 25 * L.SMS))
            sidx = np.nonzero((M.TK[e:x25] < 0) & (M.SL[e:x25] >= 0.3e9))[0]
            outs["sell03_c25"] = (M.CC[e + sidx[0]] + D) if len(sidx) else t_in + 25 * L.SMS
            for g in G:
                if g is not None and jump > g:
                    fails[g] += 1
                    for ex in EX: res[(g, ex)].append(-7.3e3)
                    continue
                for ex in EX:
                    res[(g, ex)].append(L.trip(M, [t_in], [max(outs[ex], t_in + 1)])[0])
            # followers in hold (fix K)
            x = int(M.idx(t_in + K * L.SMS))
            sl = np.arange(e, x)
            sl = sl[M.TK[sl] > 0]
            if len(sl):
                u = M.U[sl]; sp = -M.SL[sl].astype(np.float64) / 1e9
                isl = np.isin(u, list(lid))
                np.add.at(fol, np.where(isl, 3, cls[u]), sp)
            foln += 1
    hrs = L.hours(t) - 2
    out = {"run": run, "K": K, "D": D, "hours": round(hrs, 2), "events": foln,
           "follower_buy_SOL_per_trade": {n: round(fol[k] / max(foln, 1), 3) for k, n in enumerate(["BOT", "MID", "RET", "leaders"])},
           "fails": {str(g): fails[g] for g in G}, "rows": []}
    for (g, ex), v in res.items():
        s = L.stats(v); s.update(guard=str(g), exit=ex, per_day=round(s["net"] / hrs * 24, 2)); out["rows"].append(s)
    print(json.dumps(out))
    return out

if __name__ == "__main__":
    o = main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 70)
    json.dump(o, open(f"{L.OUT}/n8_{sys.argv[1].split('/')[-1].replace('.json','')}_{o['run']}_D{o['D']}.json", "w"))

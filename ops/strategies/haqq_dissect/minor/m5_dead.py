#!/usr/bin/env python3
"""MINOR step 5 (read-only): bot 234 ("dead-curve") universe and entry rule.
Candidate = an outside sell (not haqq, not our wallets) that leaves the curve at <= 30.6 SOL (back at / below the launch price),
non-mayhem, token age <= 30 min, usable tape hour (dv8 hours.json). Features are causal (rows up to and including the sell):
  vpost (curve SOL after), drop, sell SOL, age (s), peak curve SOL before, peak multiple (peak / 30), n trades / wallets before,
  n earlier floor touches on the mint, seller class (dev / bundler (create slot) / early (<= 10 slots) / other), seller's sold
  share of his buys (= exited fully?), outside buy SOL in the last 10 slots, seconds since the last outside buy, dev sold before.
Label = a code-234 lot on the mint <= 2 slots after the candidate, whose latest preceding candidate is this one.
Rule = greedy <= 4-threshold conjunction maximising F1 on D0-D2; held-out test D3-D5.
Out: minor/m5.txt, minor/m5.npz"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/minor")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import Out
from m3_entry import search, f1
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
FLOOR = 30.6e9


def main():
    t0 = time.time()
    P = Out(f"{OUT}/m5.txt")
    ids, idm = L.ids_map(); h = idm[L.HAQQ]; ours = [idm[w] for w in L.WAL.values() if w in idm]
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    cols = {k: np.asarray(T[k]) for k in ("slot", "idx", "mint", "user", "buy", "sol", "vsol", "bt")}
    n = len(cols["slot"])
    o = np.argsort(cols["mint"], kind="stable")
    for k in cols: cols[k] = cols[k][o]
    sl = cols["slot"].astype(np.int64); ix = cols["idx"].astype(np.int64); mi = cols["mint"]; us = cols["user"]; bu = cols["buy"].astype(bool)
    so = cols["sol"] / 1e9; vs = cols["vsol"].astype(np.float64); bt = cols["bt"].astype(np.int64)
    del cols
    um, st = np.unique(mi, return_index=True); en = np.append(st[1:], n)
    vsp = np.empty(n); vsp[1:] = vs[:-1]; vsp[st] = 30e9
    outside = (us != h) & ~np.isin(us, ours)
    cand = np.flatnonzero(outside & ~bu & (vs <= FLOOR) & (vsp > vs) & (vs > 1e9))
    print(f"tape {n:,}; floor sells {len(cand):,} ({time.time() - t0:.0f}s)", flush=True)
    CR = json.load(open(f"{L.TAB}/creates.json"))
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    seg = np.searchsorted(st, cand, side="right") - 1
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    l234 = collections.defaultdict(list)
    for l in lots:
        if l["code"] == 234: l234[idm.get(l["ms"])].append(l)
    F = collections.defaultdict(list); lab = []; lnet = []; meta = []
    bym = collections.defaultdict(list)
    for c, g in zip(cand.tolist(), seg.tolist()): bym[g].append(c)
    for g, cl in bym.items():
        a, e = int(st[g]), int(en[g]); m = int(um[g]); cr = CR.get(ids[m]) or {}
        if cr.get("mayhem") or cr.get("slot") is None: continue
        cs = int(cr["slot"]); creator = idm.get(cr.get("creator"), -2)
        s_ = sl[a:e]; u_ = us[a:e]; b_ = bu[a:e]; o_ = so[a:e]; v_ = vs[a:e]; x_ = ix[a:e]
        bund = set(u_[(s_ == cs) & b_].tolist()); early = set(u_[(s_ <= cs + 10) & b_].tolist())
        peak = np.maximum.accumulate(v_)
        isout = outside[a:e]
        cbo = np.cumsum(np.where(b_ & isout, o_, 0.0))
        hl = sorted(l234.get(m, []), key=lambda l: (l["slot"], l["idx"]))
        prev_touch = 0
        rows = [c - a for c in cl]
        for r in rows:
            if (s_[r] - cs) * 0.212 > 1800: continue
            hstart = (bt[a + r] + 18000) // 3600 * 3600 - 18000
            if hstart not in good: prev_touch += 1; continue
            seller = int(u_[r])
            sb = o_[:r + 1][(u_[:r + 1] == seller) & b_[:r + 1]].sum(); ss = o_[:r + 1][(u_[:r + 1] == seller) & ~b_[:r + 1]].sum()
            lo10 = int(np.searchsorted(s_, s_[r] - 10))
            lb = np.flatnonzero(b_[:r] & isout[:r])
            dev_sold = bool(((u_[:r] == creator) & ~b_[:r]).any())
            F["vpost"].append(v_[r] / 1e9); F["drop"].append(1 - (v_[r] / (v_[r - 1] if r > 0 else 30e9)) ** 2)
            F["sell_sol"].append(o_[r]); F["age_s"].append((s_[r] - cs) * 0.212); F["peak"].append(peak[r] / 1e9)
            F["n_tr"].append(r); F["n_wal"].append(len(np.unique(u_[:r + 1]))); F["touch_before"].append(prev_touch)
            F["d_dev"].append(seller == creator); F["d_bund"].append(seller in bund and seller != creator)
            F["d_early"].append(seller in early and seller not in bund and seller != creator)
            F["sold_share"].append(ss / max(sb, 1e-9)); F["b10"].append(cbo[r] - (cbo[lo10 - 1] if lo10 > 0 else 0.0))
            F["last_buy_s"].append((s_[r] - s_[lb[-1]]) * 0.212 if len(lb) else 999.0); F["dev_sold"].append(dev_sold)
            F["buys_total"].append(cbo[r])
            # label: first 234 lot after this row within 2 slots
            y = False; ln = 0.0
            for l in hl:
                if (l["slot"], l["idx"]) <= (int(s_[r]), int(x_[r])): continue
                if l["slot"] - s_[r] > 2: break
                # latest candidate before the lot must be this one
                later = [rr for rr in rows if rr > r and (int(s_[rr]), int(x_[rr])) < (l["slot"], l["idx"])]
                if later: break
                y = True; ln += l["net"]; break
            lab.append(y); lnet.append(ln); meta.append((m, int(s_[r]), int(x_[r]), int(bt[a + r])))
            prev_touch += 1
    X = np.array([F[k] for k in F], float).T; names = list(F.keys())
    y = np.array(lab); yn = np.array(lnet); meta = np.array(meta, np.int64)
    day = (meta[:, 3] - L.DAY0) // 86400
    np.savez(f"{OUT}/m5.npz", X=X, names=np.array(names), y=y, yn=yn, meta=meta, day=day)
    n234 = sum(len(v) for v in l234.values())
    P(f"# Bot 234: dead-curve universe (outside sells leaving the curve <= 30.6 SOL, age <= 30 min, usable hours, non-mayhem)")
    P(f"candidates {len(y):,}; 234 lots in total {n234:,}; labelled (bought <= 2 slots after) {y.sum():,} ({100 * y.mean():.2f}%), his net on them {yn[y].sum():+.2f}")
    P("per day candidates / bought: " + ", ".join(f"D{d} {int((day == d).sum())}/{int((y & (day == d)).sum())}" for d in range(7)))
    for k in ("vpost", "drop", "sell_sol", "age_s", "peak", "n_tr", "touch_before", "sold_share", "b10", "last_buy_s"):
        j = names.index(k)
        qs = np.percentile(X[:, j], [10, 50, 90]); qb = np.percentile(X[y, j], [10, 50, 90])
        P(f"- {k}: all p10/50/90 {qs.round(3).tolist()} | bought {qb.round(3).tolist()}")
    for k in ("d_dev", "d_bund", "d_early", "dev_sold"):
        j = names.index(k); v = X[:, j] > 0.5
        P(f"- {k}: share all {100 * v.mean():.0f}% | bought {100 * v[y].mean():.0f}% | buy rate when true {100 * y[v].mean():.1f}% vs false {100 * y[~v].mean():.1f}%")
    tr = np.isin(day, (0, 1, 2)); te = np.isin(day, (3, 4, 5))
    conds, m, best = search(X, y, names, list(range(len(names))), tr)
    P(f"\nRULE (train D0-D2): " + " AND ".join(f"{a} {s} {t:.3g}" for a, t, s in conds) + f" | train F1 {best[0]:.2f} P {100 * best[1]:.0f}% R {100 * best[2]:.0f}%")
    for d in (3, 4, 5):
        dd = day == d; _, p, r = f1(y[dd], m[dd])
        P(f"  TEST D{d}: precision {100 * p:.0f}% recall {100 * r:.0f}% (hits {int(m[dd].sum())}, bought {int(y[dd].sum())})")
    _, p, r = f1(y[te], m[te]); P(f"  TEST D3-D5: precision {100 * p:.0f}% recall {100 * r:.0f}%")
    P(f"  his net on caught {yn[y & m].sum():+.2f} ({int((y & m).sum())}) vs missed {yn[y & ~m].sum():+.2f} ({int((y & ~m).sum())})")
    np.save(f"{OUT}/m5_rule.npy", m)
    P.save(); print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()

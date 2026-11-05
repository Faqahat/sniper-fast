#!/usr/bin/env python3
"""NEWSTRAT LEADFOL scorer: copy the BUYS of a frozen list of 'leader' wallets whose buys are followed by other buyers,
land +D ms after the leader's buy, sell a fixed K slots after our entry. One position per mint.
Leader rule (all from the SELECTION days only): wallet has >= NMIN qualifying buys (>= 0.05 SOL, non-mayhem mint launched in the
run, >= 2 h into the run) on EVERY selection day and the paper follower P&L (0.55 SOL, D=70, exit K slots, 18 mSOL costs) of its
buys is >= 0 on EVERY selection day.
usage: n7_leadfol.py SEL_DAYS(comma runs) TARGET_RUN K NMIN [tag]   -> prints + OUT/n7_<tag>_<target>.json"""
import sys, json, hashlib
import numpy as np
import nlib as L
from n5_scan import ev, one_pos

def leaders(sel, K, NMIN):
    key = f"d70k{K}"; per = []
    for r in sel:
        d = ev(r); names = d["users"][d["u"]]
        uu, inv = np.unique(names, return_inverse=True)
        n = np.bincount(inv); s = np.bincount(inv, weights=d[key].astype(np.float64))
        per.append({u: (n[j], s[j]) for j, u in enumerate(uu)})
    return sorted(set.intersection(*[set(u for u, (n, s) in p.items() if n >= NMIN and s >= 0) for p in per]))

def score(target, lead, K, hrs_override=None):
    d = ev(target); la = L.launches(target)
    names = d["users"][d["u"]]
    idx = np.nonzero(np.isin(names, lead))[0]
    idx = idx[one_pos(d["m"][idx], d["cc"][idx], K, 70)]
    hrs = d["hours"]
    mints = d["mints"][d["m"][idx]]
    isdev = np.array([la.get(str(m), {}).get("creator") == str(u) for m, u in zip(mints, names[idx])])
    out = {"hours": round(hrs, 2), "n_leaders": len(lead), "active": int(len(np.unique(names[idx])))}
    for D in (0, 50, 70, 90):
        v = d[f"d{D}k{K}"][idx].astype(np.float64)
        s = L.stats(v); s["per_day"] = round(s["net"] / hrs * 24, 2); out[f"D{D}"] = s
    v70 = d[f"d70k{K}"][idx].astype(np.float64)
    if f"f20k{K}" in d:
        out["f20_day"] = round(float(d[f"f20k{K}"][idx].sum()) / 1e9 / hrs * 24, 2)
    for lab, msk in (("devbuy", isdev), ("trader", ~isdev)):
        s = L.stats(v70[msk]); s["per_day"] = round(s["net"] / hrs * 24, 2); out[lab] = s
    # concentration by leader
    uu, inv = np.unique(names[idx], return_inverse=True)
    sl = np.bincount(inv, weights=v70) / 1e9
    o = np.argsort(sl)[::-1]
    out["top_leaders"] = [(str(uu[j]), int((inv == j).sum()), round(float(sl[j]), 2)) for j in o[:8]]
    out["wo_top3_leaders_day"] = round(float(sl[o[3:]].sum()) / hrs * 24, 2)
    out["leaders_pos"] = int((sl > 0).sum())
    # by 6-hour block
    t0 = d["cc"].min()
    blk = ((d["cc"][idx] - t0) // (6 * 3600e3)).astype(int)
    out["blocks6h"] = [round(float(v70[blk == b].sum()) / 1e9, 2) for b in range(blk.max() + 1)] if len(blk) else []
    return out

if __name__ == "__main__":
    sel = sys.argv[1].split(","); target = sys.argv[2]; K = int(sys.argv[3]); NMIN = int(sys.argv[4])
    tag = sys.argv[5] if len(sys.argv) > 5 else "x"
    lead = leaders(sel, K, NMIN)
    o = score(target, lead, K)
    o.update(sel=sel, K=K, NMIN=NMIN, leaders_sha=hashlib.sha256("\n".join(lead).encode()).hexdigest())
    json.dump({"res": o, "leaders": lead}, open(f"{L.OUT}/n7_{tag}_{target}.json", "w"))
    print(json.dumps(o, indent=None))

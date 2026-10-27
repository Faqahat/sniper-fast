#!/usr/bin/env python3
"""LIVE28 extra checks (INFERRED vs MEASURED):
  (1) P&L at the live fill slot: for each live-filled window, the cal draws whose fill landed in the same slot as the live fill;
      replay P&L (pnl - close fee) vs live (realized + rent back);
  (2) the tail: per skipped / stopped window, the share of draws where the counterfactual window nets > +0.03 SOL.
usage: samefill28.py POOL [TAG]"""
import sys, os, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib28 as L
import effects28 as E
RENT = 5020

if __name__ == "__main__":
    pool = sys.argv[1] if len(sys.argv) > 1 else "P3"; tag = sys.argv[2] if len(sys.argv) > 2 else "main"
    Z = pickle.load(open(f"{L.DATA}/replay28_{pool}_{tag}.pkl", "rb"))
    R = L.load_run()
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}
    a, b, n_same = [], [], []
    for k, x in lv.items():
        if not x["live"]["filled"]: continue
        fs = R["W"][k[1]]["fill"]["slot"]
        v = [by[k]["pnl"] - RENT for _, by in Z["out"]["cal"] if by[k]["filled"] and by[k]["fill_S"] == fs]
        if not v: continue
        a.append((x["live"]["pnl"] + x["live"]["rb"]) / 1e9); b.append(np.mean(v) / 1e9); n_same.append(len(v))
    a = np.array(a); b = np.array(b)
    nf = sum(1 for x in lv.values() if x["live"]["filled"])
    print(f"(1) live-filled windows with >= 1 draw filled in the live fill slot: {len(a)} of {nf} (median {np.median(n_same):.0f} such draws each)")
    print(f"    P&L per fill at the live fill slot: live {a.mean():+.4f} vs replay {b.mean():+.4f}; sum live {a.sum():+.4f} vs replay {b.sum():+.4f}; "
          f"corr {np.corrcoef(a, b)[0, 1]:.2f}; same sign {np.mean(np.sign(a) == np.sign(b)) * 100:.0f}%")
    w = a > 0
    print(f"    live winners {w.sum()}: live {a[w].sum():+.4f} vs replay at the same slot {b[w].sum():+.4f}; live losers {(~w).sum()}: live {a[~w].sum():+.4f} vs replay {b[~w].sum():+.4f}")
    # (2) tails
    print("(2) skipped / stopped windows with P(counterfactual net > +0.03) >= 2% of draws:")
    rows = []
    for x in M["skip"]:
        k = x["key"]; v = np.array([E.adj_net(by[k]) for _, by in Z["out"]["C"]]) / 1e9
        rows.append((f"S{k[1]} (skip)", x["t_ns"], x["mint"], (v > 0.03).mean(), v[v > 0.03].mean() if (v > 0.03).any() else 0.0, v.mean()))
    for k, x in lv.items():
        if x["d_stop"] is None: continue
        v = np.array([E.adj_net(by[k]) if by.get(k) else 0.0 for _, by in Z["out"]["D"]]) / 1e9
        rows.append((f"w{k[1]} (stop)", x["t_ns"], x["mint"], (v > 0.03).mean(), v[v > 0.03].mean() if (v > 0.03).any() else 0.0, v.mean()))
    for r in sorted(rows, key=lambda r: -r[3]):
        if r[3] >= 0.02: print(f"    {r[0]:12s} {L.hm(r[1])} {r[2][:8]} P(>+0.03) {r[3] * 100:4.0f}%  mean when > +0.03: {r[4]:+.4f}  window mean {r[5]:+.4f}")

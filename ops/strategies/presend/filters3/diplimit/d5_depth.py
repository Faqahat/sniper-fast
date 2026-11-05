#!/usr/bin/env python3
"""DIPLIMIT step 5 [MEASURED]: live fills by fill depth (1 - entry price / signing price) and their realized P&L; shows which live
fills a deeper limit keeps on the same try (depth >= drop) and which it loses.  usage: d5_depth.py TAG [TAG ...]"""
import sys, pickle
D = "/home/moiz/sniper-data/filters3/diplimit"
B = [(0.12, 0.15), (0.15, 0.18), (0.18, 0.25), (0.25, 1)]
for tag in sys.argv[1:]:
    w = [x for x in pickle.load(open(f"{D}/win_{tag}.pkl", "rb"))["wins"] if x["fill"] and x["pnl"] is not None]
    print(f"== {tag}: live fills {len(w)} realized {sum(x['pnl'] for x in w):+.3f}")
    for lo, hi in B:
        z = [x for x in w if x["fill"].get("p_entry_pre") and lo <= 1 - x["fill"]["p_entry_pre"] / x["fill"]["p_sign"] < hi]
        if not z: continue
        s = sorted(x["pnl"] for x in z)
        print(f"  depth {lo:.2f}-{hi:.2f}: n {len(z):3d} realized {sum(s):+.3f} win {sum(v > 0 for v in s) / len(s):.0%} mean {sum(s) / len(s) * 1e3:+.1f} mSOL"
              f"  t2 {sum(1 for x in z if x['kind'] == 't2')} rearm {sum(1 for x in z if x['kind'] == 'rearm')}")
    nz = [x for x in w if not x["fill"].get("p_entry_pre")]
    if nz: print("  no depth field:", len(nz))

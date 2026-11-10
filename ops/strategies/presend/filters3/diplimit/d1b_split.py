#!/usr/bin/env python3
"""DIPLIMIT: split win_r42all.pkl (r42 covered by raw tape) into time chunks (PKT) -> win_r42cN.pkl (same landing pool)."""
import pickle, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/diplimit")
from d1_extract import pkt
D = "/home/it/sniper-data/filters3/diplimit"
CH = [("c1", "10-31 03:50", "10-31 10:00"), ("c2", "10-31 10:00", "10-31 16:00"), ("c3", "10-31 16:00", "10-31 19:00"),
      ("c4", "10-31 19:00", "11-01 01:00"), ("c5", "11-01 01:00", "11-01 07:00"), ("c6", "11-01 07:00", "11-01 12:00"), ("c7", "11-01 12:00", "11-01 19:05")]
A = pickle.load(open(f"{D}/win_r42all.pkl", "rb"))
for n, a, b in CH:
    lo, hi = pkt(a), pkt(b)
    w = [x for x in A["wins"] if lo <= (x["t_arm"] or 0) < hi]
    pickle.dump({"wins": w, "pool": A["pool"], "cfg": A["cfg"]}, open(f"{D}/win_r42{n}.pkl", "wb"))
    print(n, a, b, len(w), sum(1 for x in w if x["fill"]), round(sum(x["pnl"] or 0 for x in w), 3))

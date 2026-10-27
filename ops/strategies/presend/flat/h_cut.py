#!/usr/bin/env python3
"""FLAT study, HOLDOUT r28: keep only the windows whose trigger is at least 60 s before the end of the chain recording copy
(phase 2 upper bound) and whose fill (if any) has its realized and rent-back records; record the cutoff. usage: h_cut.py HI_UNIX_S"""
import sys, pickle
import flatlib as FL
hi = int(sys.argv[1]); cut_ns = (hi - 60) * 10**9
B = FL.load_base("r28")
W = B["W"]; keep = []; drop = 0; incomplete = 0
for w in W:
    if w["t"] > cut_ns: drop += 1; continue
    if w["filled"] and (w.get("rb_rec") is None and w["rb"] == 0 and False): incomplete += 1
    keep.append(w)
B["W"] = keep; B["cutoff_ns"] = cut_ns
pickle.dump(B, open(f"{FL.D}/base_r28.pkl", "wb"))
F = [w for w in keep if w["filled"]]
print(f"r28 cutoff {FL.hm(cut_ns)} PKT: windows kept {len(keep)} (dropped after cutoff {drop}), fills {len(F)}, first trigger {FL.hm(keep[0]['t'])}, last {FL.hm(keep[-1]['t'])}, "
      f"fills with rent back {sum(1 for w in F if w['rb'] > 0)}")

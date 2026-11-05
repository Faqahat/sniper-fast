#!/usr/bin/env python3
"""FLATPERFECT step 3 [PAPER universe, chain-wide]: every T2-like trigger on the recorded chain BEFORE run 55's first arm slot
(buy >= 6% supply, vSOL before >= 30, >= 1.4 SOL, token age >= 2 slots, not ours), with a 12% price dip within 10 slots
(price ~ vsol^2). The 'fill' = the first dip row; buy_slot = its slot (pre-fill features stop at buy_slot - 2 like live).
Out: paper_inputs.pkl (fp1 input format with m64, whale64, dip_row)."""
import numpy as np, pickle, sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatsig")
import flib as L
D = L.D; CUT_SLOT = 465124000
z = np.load(f"{D}/chain.npz")
S, I, M, U, B = z["slot"], z["idx"], z["mint"], z["user"], z["buy"]
SOL, TOK, VS = z["sol"].astype(np.float64), z["tok"].astype(np.float64), z["vsol"].astype(np.float64)
n = len(S)
gstart = np.r_[0, np.nonzero(M[1:] != M[:-1])[0] + 1]
gid = np.zeros(n, np.int64); gid[gstart[1:]] = 1; gid = np.cumsum(gid)
first = S[gstart][gid]
OUR = np.array(sorted(L.OURS64), dtype=np.uint64)
c = np.nonzero((B == 1) & (TOK >= 0.06e15) & (VS - SOL >= 30e9) & (SOL >= 1.4e9) & (S - first >= 2) & (S < CUT_SLOT) & ~np.isin(U, OUR))[0]
print("cands", len(c), flush=True)
out = []
gend = np.r_[gstart[1:], n]
for r in c:
    e = gend[gid[r]]
    th = VS[r] * np.sqrt(0.88)
    j = r + 1
    while j < e and S[j] <= S[r] + 10:
        if VS[j] <= th and VS[j] > 0: break
        j += 1
    else:
        continue
    if j >= e or S[j] > S[r] + 10: continue
    out.append({"key": f"P|{r}", "m64": int(M[r]), "mint": None, "kind": "T2", "trig_slot": int(S[r]), "trig_idx": int(I[r]),
                "buy_slot": int(S[j]), "buy_idx": int(I[j]), "whale64": int(U[r]), "dip_row": int(j), "paper": True})
pickle.dump(out, open("/home/moiz/sniper-data/flatperfect/paper_inputs.pkl", "wb"))
print("with dip", len(out))

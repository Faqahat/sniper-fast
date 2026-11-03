#!/usr/bin/env python3
"""YOUNG step 2: per-trigger chain tape (all pump.fun trades of the mint from its first trade to trigger slot + 60).
Chain = quiet3 chain.npz (to 10-29 07:16 PKT) + young ext (to ~09:11 PKT). Out: tapes.pkl {sig: list of tuples}
tuple = (slot, idx, j, buy, sol, tok, vsol, vtok, user_str)"""
import json, pickle, numpy as np
D = "/home/moiz/sniper-data/presend_young"
T = json.load(open(f"{D}/trig.json"))["rows"]
want = {}
for r in T: want.setdefault(r["mint"], []).append(r)
out = {}
for npz, ids in (("/home/moiz/sniper-data/presend_quiet3/chain.npz", "/home/moiz/sniper-data/presend_quiet3/ids.json"),
                 (f"{D}/ext/chain.npz", f"{D}/ext/ids.json")):
    I = json.load(open(ids)); ml = I["mint"]; ul = I["user"]
    mid = {m: k for k, m in enumerate(ml) if m in want}
    z = np.load(npz)
    mint = z["mint"]
    sel = np.isin(mint, np.array(list(mid.values()), dtype=np.uint32))
    idx = np.nonzero(sel)[0]
    cols = {k: z[k][idx] for k in ("s", "i", "j", "buy", "sol", "tok", "vsol", "vtok", "mint", "user")}
    inv = {v: k for k, v in mid.items()}
    by = {}
    for n in range(len(idx)):
        m = inv[int(cols["mint"][n])]
        by.setdefault(m, []).append((int(cols["s"][n]), int(cols["i"][n]), int(cols["j"][n]), int(cols["buy"][n]), int(cols["sol"][n]), int(cols["tok"][n]),
                                     int(cols["vsol"][n]), int(cols["vtok"][n]), ul[int(cols["user"][n])]))
    for m, L in by.items():
        for r in want[m]:
            lo_ok = True
            out.setdefault(r["sig"], set()).update(x for x in L if x[0] <= r["slot"] + 60)
    print(npz, "mints hit", len(by), flush=True)
fin = {k: sorted(v) for k, v in out.items()}
pickle.dump(fin, open(f"{D}/tapes.pkl", "wb"))
print("triggers with tape", len(fin), "of", len(T))

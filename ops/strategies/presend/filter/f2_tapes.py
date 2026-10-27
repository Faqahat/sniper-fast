#!/usr/bin/env python3
"""PRESEND FILTER, step 5: per armed window, its tries and the token's tape around it, for DURING rules (stop / delay the tries).
  tries: every attempt of the window: send slot (the engine's current slot when it sent it), send time, landed result, fee if it landed
         and failed (MEASURED: land record; 'unseen' looked up on the chain), whether it is the filling try, land slot, deadline, and pos =
         the chain position of the latest trade of the token the engine had seen when it signed it (the attempt record's 'pos': what
         the engine knew of the token at that moment; a DURING rule may use the token's trades up to pos only)
  tape : the token's trades from 300 slots before the trigger to the window end + 3 slots (slot, idx, j, wallet id, buy, sol, vsol, vtok)
Writes /home/moiz/sniper-data/presend_filter/tapes.pkl  {(run, seg, w): dict(tries=[...], tape=np.ndarray, k_trig=index of the trigger)}"""
import json, pickle, time
import numpy as np
from chainlib import Chain, B
import lv

t0 = time.time()
C = Chain(cols=("s", "i", "j", "buy", "sol", "user", "vsol", "vtok"))
our_fail = {k: v[2] for k, v in json.load(open(f"{B}/our_fails.json")).items()}
out = {}
for run in lv.RUNFILES:
    R = lv.load(run)
    for (seg, w), X in R["W"].items():
        a = X["arm"]; tr = a["trig"]
        fill_sig = X["fills"][0]["sig"] if X["fills"] else None
        tries = []
        for sig in X["atts"]:
            A = R["att"][sig]; L = R["land"].get(sig) or {}
            res = L.get("res")
            fee = 0
            if res not in ("ok", None, "unseen"): fee = L.get("fee") if L.get("fee") is not None else 5120
            elif res in (None, "unseen") and sig in our_fail: fee = our_fail[sig]; res = "chain_fail"
            tries.append((A["slot"], A["t"], res, fee, sig == fill_sig, L.get("slot"), A.get("deadline"), tuple(A.get("pos") or (0, 0, 0))))
        rows = C.mint_rows(tr["mint"])
        k = C.find(rows, tr["slot"], tr["idx"], tr.get("j", 0)) if len(rows) else None
        tape = None; kt = None
        if k is not None:
            S = C.c["s"][rows]
            lo = np.searchsorted(S, tr["slot"] - 300); hi = np.searchsorted(S, a["en_slot"] + 4)
            rr = rows[lo:hi]
            tape = np.stack([C.c["s"][rr].astype(np.int64), C.c["i"][rr].astype(np.int64), C.c["j"][rr].astype(np.int64), C.c["user"][rr].astype(np.int64),
                             C.c["buy"][rr].astype(np.int64), C.c["sol"][rr].astype(np.int64), C.c["vsol"][rr].astype(np.int64), C.c["vtok"][rr].astype(np.int64)], 1)
            kt = k - lo
        out[(run, seg, w)] = dict(tries=tries, tape=tape, k_trig=kt, whale=C.wid.get(tr["wallet"]), trig_slot=tr["slot"], en_slot=a["en_slot"])
    print(run, len(R["W"]), f"{time.time() - t0:.0f}s", flush=True)
pickle.dump(dict(out=out, ours=[C.wid.get(x) for x in lv.WALLET.values()]), open(f"{B}/tapes.pkl", "wb"))
print("windows", len(out))

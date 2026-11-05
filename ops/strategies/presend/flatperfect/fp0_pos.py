#!/usr/bin/env python3
"""FLATPERFECT step 0: DEV position list (r37..r54) from the flatsig f2 extracts -> inputs for fp1 (no outcomes) + outcomes file."""
import sys, pickle; sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import base
P = base.positions()
inp = []
for p in P:
    p["key"] = f'{p["run"]}|{p["mint"]}|{p["pid"]}|{p["kind"]}|{p["w"]}'
    inp.append({k: p.get(k) for k in ("key", "mint", "kind", "trig_slot", "trig_idx", "buy_slot", "buy_idx", "whale")})
pickle.dump(inp, open(f"{base.OUT}/dev_inputs.pkl", "wb"))
pickle.dump(P, open(f"{base.OUT}/dev_pos.pkl", "wb"))
print(len(P))

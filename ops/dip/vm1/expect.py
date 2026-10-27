#!/usr/bin/env python3
"""VM1 independent check, step 6: per-dump expected trade values for every landing row (all eligible dumps, 0.3 SOL).
Rows: L-live (block-clock delays of our live buys r10+, paired with live hold-5/6 sell landings), F40/F80/F150
(fixed txs after the dump, spill-aware, live sell landings), CLAIM (the copy's rule: +80 txs never leaving the dump's
slot, exit at the end of dump slot + 6; one deterministic sample). Writes /home/moiz/sniper-data/vm1/expect.npz"""
import json, sys, time
import numpy as np
import core, sim

if __name__ == "__main__":
    S = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
    D = core.Data(); z = np.load(core.D + "/dumps.npz")
    cal = json.load(open(core.D + "/livecal.json"))
    deltas = np.array(cal["deltas"]); exits = [tuple(e) for e in cal["exits"]]
    elig = (~z["hole"]) & z["full"]
    kd = z["k"][elig]
    out = {"elig_idx": np.where(elig)[0]}
    exs = [("live", a, b) for a, b in exits]
    rows = {"Llive": [("clock", d) for d in deltas]}
    for N in (40, 80, 150):
        rows[f"F{N}"] = [("fixed", N)]
    for name, ent in rows.items():
        t = time.time()
        if len(ent) == 1:          # fixed entry: average over the live exit samples
            acc = None
            for xs in exs:
                fl, p, se, sx = sim.trade(D, kd, ent[0], xs, S)
                e = {"p_fill": fl.astype(float), "e_pos": np.maximum(p, 0), "e_neg": np.minimum(p, 0), "p_spill": (se > z["slot"][elig]).astype(float)}
                acc = e if acc is None else {k: acc[k] + e[k] for k in acc}
            E = {k: v / len(exs) for k, v in acc.items()}
        else:
            E = sim.expected(D, kd, ent, exs, S)
        for k, v in E.items(): out[f"{name}_{k}"] = v
        print(name, f"{time.time() - t:.0f}s", "fill", E["p_fill"].mean().round(3), "spill", E["p_spill"].mean().round(3), flush=True)
    fl, p, se, sx = sim.trade(D, kd, ("claim",), ("claim",), S)
    out["CLAIM_fill"] = fl; out["CLAIM_pnl"] = p
    np.savez(core.D + f"/expect_{S}.npz", **out)
    print("saved")

#!/usr/bin/env python3
"""DIPML step 2: per-dump expected replay P&L (before tx costs) for every latency row x size x follower cut.
Tape = counterfactual (our own live trades removed, later states shifted; livecal.counterfactual).
Entry landing: the MEASURED live delay distribution (block clock, dump -> our landed buy) of fires before TEST
(dump slot <= B_VAL), scaled so its median = the row's latency (35/50/58/75 ms); 61 quantiles; spill into the next
block happens naturally. Exit: live sell landings (hold 5/6) of the same pre-TEST fires. Guard 1.05 (live).
phi: share of other wallets' buy SOL between our entry and exit removed (20% fewer followers).
Writes /home/moiz/sniper-data/dipml/expect.npz: for each key 'L{ms}_S{size}_F{phi}': pf (fill prob), ev (mean pnl pre-cost)."""
import json, sys, numpy as np
from multiprocessing import Pool
import core, sim, livecal
from feat import B_VAL

LATS = (35, 50, 58, 75); SIZES = (0.35, 0.5, 0.75, 1.0); PHIS = (0.0, 0.2)
W = ["2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"]
G = {}

def trade_phi(E, kd, es, xs, S, phi, guard=1.05):
    T = E.T; m = T["mint"][kd]
    Vd = T["vsol"][kd].astype(np.float64); Td = T["vtok"][kd].astype(np.float64)
    f = (T["fee_bps"][kd].astype(np.float64) + T["cfee_bps"][kd].astype(np.float64)) / 1e4
    se, ie = sim.entry_positions(E, kd, es)
    ke = E.state_before(m, se, ie); ke = np.where(ke < kd, kd, ke)
    Ve = T["vsol"][ke].astype(np.float64); Te = T["vtok"][ke].astype(np.float64); K = Ve * Te
    x = S * 1e9 / (1 + f); q = Te - K / (Ve + x); qd = Td - (Vd * Td) / (Vd + x)
    filled = q >= qd / guard
    sx, ix = sim.exit_positions(E, kd, se, xs)
    kx = E.state_before(m, sx, ix); kx = np.where(kx < ke, ke, kx)
    Vx = T["vsol"][kx].astype(np.float64) - phi * (G["CB"][kx] - G["CB"][ke])
    V2 = Vx + x
    out = V2 - K / (K / V2 + q)
    return filled, np.where(filled, out * (1 - f) / 1e9 - S, 0.0)

def job(a):
    L, S, phi = a
    E = G["E"]; kd = G["kd"]; d = G["d"] * (L / G["med"]); exs = G["exs"]
    pf = np.zeros(len(kd)); ev = np.zeros(len(kd))
    for j, dd in enumerate(d):
        fl, p = trade_phi(E, kd, ("clock", dd / 212.07), exs[(j * 7919) % len(exs)], S, phi)
        pf += fl; ev += p
    return f"L{L}_S{S}_F{phi}", pf / len(d), ev / len(d)

def main():
    D = core.Data()
    F = json.load(open(core.D + "/live_fires.json"))
    pre = [f for f in F if f.get("dump_slot", 1 << 62) <= B_VAL and "buy_slot" in f]
    dl, ex = livecal.landing_samples(D, pre)
    dms = dl * 212.07
    print(f"pre-TEST live landings {len(dms)} median {np.median(dms):.1f} ms p25 {np.percentile(dms, 25):.1f} p75 {np.percentile(dms, 75):.1f}; exits {len(ex)}", flush=True)
    E, ours = livecal.counterfactual(D, W)
    z = np.load(core.D + "/dumps.npz")
    key = core.pack(D.T["mint"], D.T["slot"], D.T["idx"], D.T["j"])[z["k"]]
    keyE = core.pack(E.T["mint"], E.T["slot"], E.T["idx"], E.T["j"])
    kdE = np.minimum(np.searchsorted(keyE, key), len(keyE) - 1); ok = keyE[kdE] == key
    print("dumps in counterfactual tape", ok.mean(), flush=True)
    # cumulative other-wallet buy SOL per row within the mint (rows sorted by mint, chain order)
    b = np.where(E.T["buy"] == 1, E.T["sol"].astype(np.float64), 0.0); cs = np.cumsum(b)
    G.update(E=E, kd=kdE, d=np.quantile(dms, np.linspace(0.008, 0.992, 61)), med=float(np.median(dms)),
             exs=[("live", a, bb) for a, bb in ex], CB=cs)
    del D
    jobs = [(L, S, p) for L in LATS for S in SIZES for p in PHIS]
    out = {"ok": ok, "live_delays_ms": dms}
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 6) as P:
        for name, pf, ev in P.imap_unordered(job, jobs):
            out[name + "_pf"] = pf; out[name + "_ev"] = ev
            print(name, "fill", pf[ok].mean().round(3), "ev mSOL", (ev[ok].mean() * 1e3).round(2), flush=True)
    np.savez(core.D + "/expect.npz", **out)
    print("saved")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""VM1 independent check, step 5: live calibration on our real fires (chain truth), read-only.
  (a) math check at the ACTUAL chain positions on the real tape: guard call, tokens received, SOL out of our sell
  (b) my simulator's prediction for each fired dump (L-live landing mixture, live exits) on the tape WITHOUT our own
      trades (counterfactual: our net SOL removed from the curve), vs the realized chain P&L
  (c) the copy's paper rule (+80 txs, never spilling, end of dump slot + 6, 0.6/2 mSOL) on the same dumps vs realized
  (d) VM1 score of each fired dump (my features on the real tape) and realized P&L by VM1 pick / no pick
Writes /home/moiz/sniper-data/vm1/livecal.json and prints the tables."""
import json, copy, sys, collections
import numpy as np
import core, sim

def landing_samples(D, fires):
    """block-clock delays (slot units) of every landed buy and live sell samples (dslot after buy slot, block fraction)"""
    d = []; ex = []
    for f in fires:
        if "dump_slot" not in f or "buy_slot" not in f: continue
        d.append(float(D.clock(np.array([f["buy_slot"]]), np.array([f["buy_idx"]]))[0] - D.clock(np.array([f["dump_slot"]]), np.array([f["dump_idx"]]))[0]))
        if f["buy_ok"] and f.get("hold_slots") in (5, 6):
            ok = [s for s in f["sell_txs"] if s["ok"]]
            if ok:
                s = ok[0]; ex.append((s["slot"] - f["buy_slot"], s["idx"] / max(int(D.bsize(np.array([s["slot"]]))[0]), 1)))
    return np.array(d), ex

def counterfactual(D, wallets):
    """a copy of D without our wallets' trades; later states of the same token shifted by our net SOL in the curve"""
    T = D.T; ours = np.isin(T["user"], [D.users.index(w) for w in wallets if w in D.users])
    sgn = np.where(T["buy"] == 1, 1, -1).astype(np.int64)
    net = np.where(ours, sgn * T["sol"].astype(np.int64), 0)
    # cumulative net per mint (rows are sorted by mint, chain order)
    cs = np.cumsum(net); first = D.mstart[T["mint"]]
    base = np.where(first > 0, cs[np.maximum(first - 1, 0)], 0); base = np.where(first == 0, 0, base)
    cum = cs - base                                      # our net SOL in this token's curve up to and incl. this row
    V = T["vsol"].astype(np.float64) - cum; K = T["vsol"].astype(np.float64) * T["vtok"].astype(np.float64)
    T2 = T.copy(); T2["vsol"] = np.round(V).astype(np.uint64); T2["vtok"] = np.round(K / V).astype(np.uint64)
    keep = ~ours
    E = copy.copy(D); E.T = T2[keep]; E.G = D.G[keep]
    mm = E.T["mint"]; E.mstart = np.searchsorted(mm, np.arange(len(D.mints)), "left"); E.mend = np.searchsorted(mm, np.arange(len(D.mints)), "right")
    return E, ours

def main():
    D = core.Data(); M = core.Model()
    F = json.load(open(core.D + "/live_fires.json"))
    W = ["2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"]
    cur = [f for f in F if f["run"] >= 10 and "dump_slot" in f and "buy_slot" in f]
    deltas, exits = landing_samples(D, cur)
    print(f"L-live: {len(deltas)} landings, median {np.median(deltas) * core.SLOT_SEC * 1e3:.1f} ms; live sells for hold 5/6: {len(exits)}")
    # locate dumps in my universe (real tape)
    key = core.pack(D.T["mint"], D.T["slot"], D.T["idx"], D.T["j"])
    mint_id = {m: q for q, m in enumerate(D.mints)}
    rows = []
    for f in F:
        if "dump_slot" not in f or "buy_slot" not in f: continue
        mid = mint_id.get(f["mint"])
        if mid is None: continue
        g = core.pack(mid, f["dump_slot"], f["dump_idx"], f["dump_j"]); q = np.searchsorted(key, g)
        if q < len(key) and key[q] == g: rows.append((f, int(q)))
    print(f"fires {len(F)} | dump in my clean universe: {len(rows)}")
    E, ours = counterfactual(D, W)
    keyE = core.pack(E.T["mint"], E.T["slot"], E.T["idx"], E.T["j"])
    kd = np.array([q for _, q in rows]); kdE = np.minimum(np.searchsorted(keyE, key[kd]), len(keyE) - 1)
    okm = keyE[kdE] == key[kd]; print("dropped (dump not in counterfactual tape)", (~okm).sum())
    rows = [r for r, o in zip(rows, okm) if o]; kd = kd[okm]; kdE = kdE[okm]
    spend = np.array([f["spend"] / 1e9 for f, _ in rows])
    real = np.array([f["chain_pnl"] for f, _ in rows]); ok = np.array([f["buy_ok"] for f, _ in rows])
    cost_f = np.array([((f["buy_fee"] + f["buy_tips"]) + sum(s["fee"] + s["tips"] for s in f["sell_txs"])) / 1e9 for f, _ in rows])
    # (a) actual positions on the counterfactual tape: guard call + tokens + exit
    fl_a = np.zeros(len(rows), bool); pnl_a = np.zeros(len(rows)); tok_err = []
    for r, (f, q) in enumerate(rows):
        kk = np.array([kdE[r]])
        es = ("clock", float(D.clock(np.array([f["buy_slot"]]), np.array([f["buy_idx"]]))[0] - D.clock(np.array([f["dump_slot"]]), np.array([f["dump_idx"]]))[0]))
        okx = [s for s in f["sell_txs"] if s["ok"]]
        xs = ("live", okx[0]["slot"] - f["buy_slot"], okx[0]["idx"] / max(int(D.bsize(np.array([okx[0]["slot"]]))[0]), 1)) if okx else ("live", 4, 0.39)
        fl, p, se, sx = sim.trade(E, kk, es, xs, S=spend[r])
        fl_a[r] = fl[0]; pnl_a[r] = p[0]
    guard_match = (fl_a == ok).mean()
    print(f"(a) actual positions: guard call matches chain on {guard_match * 100:.1f}% of {len(rows)} fires "
          f"(sim fill {fl_a.mean():.2f} vs real {ok.mean():.2f})")
    both = fl_a & ok
    simv = pnl_a[both] - cost_f[both]
    print(f"    filled in both n={both.sum()}: sim (no follower cut, actual tx costs) {simv.sum():+.4f} vs realized {real[both].sum():+.4f} SOL "
          f"(per fill {simv.mean() * 1e3:+.2f} vs {real[both].mean() * 1e3:+.2f} mSOL)")
    # (b) L-live mixture (what the simulator would have predicted before firing)
    ent = [("clock", d) for d in deltas]; exs = [("live", a, b) for a, b in exits]
    res = {}
    Eall = {k: np.zeros(len(rows)) for k in ("p_fill", "e_pos", "e_neg", "p_spill")}
    for sp in np.unique(spend):                          # each fire at its own size
        sel = spend == sp; Ex = sim.expected(E, kdE[sel], ent, exs, S=float(sp))
        for k in Eall: Eall[k][sel] = Ex[k]
    for name, rsel in (("r10+", np.array([f["run"] >= 10 for f, _ in rows])), ("all", np.ones(len(rows), bool))):
        Ex = {k: v[rsel] for k, v in Eall.items()}
        for cut in (0.0, 0.2, 0.35):
            v = sim.value(Ex, 0.00379, 0.0006, cut)
            res[(name, cut)] = (v.sum(), real[rsel].sum(), rsel.sum())
            print(f"(b) {name:4s} L-live sim, cut {int(cut * 100):2d}%, 3.79/0.6 mSOL: {v.sum():+.4f} SOL vs realized {real[rsel].sum():+.4f} over {rsel.sum()} fires "
                  f"(per fire {v.mean() * 1e3:+.2f} vs {real[rsel].mean() * 1e3:+.2f} mSOL) | sim fill {Ex['p_fill'].mean():.2f} vs real {ok[rsel].mean():.2f}")
    # (c) the copy's paper rule on the same dumps
    for C, Rv in ((0.002, 0.0005), (0.0006, 0.00015)):
        fl, p, _, _ = sim.trade(E, kdE, ("claim",), ("claim",), S=0.3)
        v = sim.claim_value(fl, p, C, Rv) * (spend / 0.3)
        print(f"(c) CLAIM paper (+80 txs same slot, end of dump slot+6, {C * 1e3:.1f} mSOL, revert {Rv * 1e3:.2f}): {v.sum():+.4f} SOL vs realized {real.sum():+.4f} "
              f"over {len(rows)} fires (fill {fl.mean():.2f} vs real {ok.mean():.2f})")
    # (d) VM1 on the fired dumps
    X = core.features(D, kd, "model"); s = M.score(X); pk = s >= M.cut
    print(f"(d) VM1 picks among fired dumps: {pk.sum()} of {len(rows)} | realized per fire: picked {real[pk].mean() * 1e3 if pk.any() else float('nan'):+.2f} mSOL "
          f"(fills {ok[pk].sum()}) vs not picked {real[~pk].mean() * 1e3:+.2f} (fills {ok[~pk].sum()})")
    for qq in (0.5, 0.75, 0.9):
        c = np.quantile(s, qq); hi = s >= c
        print(f"    VM1 score top {int((1 - qq) * 100)}% of fired dumps (score >= {c:.3f}): realized per fire {real[hi].mean() * 1e3:+.2f} mSOL (n={hi.sum()}, fills {ok[hi].sum()}) vs rest {real[~hi].mean() * 1e3:+.2f} (n={(~hi).sum()})")
    json.dump({"rows": [{"delay_ms": float((D.clock(np.array([f["buy_slot"]]), np.array([f["buy_idx"]]))[0] - D.clock(np.array([f["dump_slot"]]), np.array([f["dump_idx"]]))[0]) * 212.07), "cost": float(cost_f[r]), "region": f["region"], "run": f["run"], "mint": f["mint"], "dump_sig": f["dump_sig"], "spend": f["spend"], "buy_ok": f["buy_ok"],
                         "real": f["chain_pnl"], "sim_fill_actualpos": bool(fl_a[r]), "sim_pnl_actualpos": float(pnl_a[r]), "vm1": float(s[r]),
                         "vm1_pick": bool(pk[r]), "eng_m2": f.get("eng_m2"), "eng_m2_pick": f.get("eng_m2_pick"), "eng_imit_pass": f.get("eng_imit_pass")}
                        for r, (f, q) in enumerate(rows)], "deltas": deltas.tolist(), "exits": exits}, open(core.D + "/livecal.json", "w"))

if __name__ == "__main__":
    main()

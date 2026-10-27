#!/usr/bin/env python3
"""DIPML step 2b: recorded hours per split + replay-vs-live calibration on our real reactive fires.
For every live fire whose dump is in the dump table: replay value at the fire's own size (interpolated over the size
grid) at the live-median latency row (mean of the L50 and L58 rows ~ live median 54 ms), our tx cost model, vs the
chain-measured P&L (all fees/tips, MEASURED). Penalty = mean(replay - live) per attempt, frozen from PRE-TEST fires.
Also reports: the same on TEST-period fires (check only), measured live landing per period, the actual-position
check from livecal.json. Writes hours.json, calib.json."""
import json, numpy as np, collections
import core
from feat import B_TRAIN, B_VAL

C, R = 0.0046, 0.0006

def main():
    S = np.load(core.D + "/slots.npy"); holes = json.load(open(core.D + "/holes.json"))
    lo, hi = int(S["slot"].min()), int(S["slot"].max())
    def hrs(a, b):
        n = b - a + 1 - sum(max(0, min(b, y) - max(a, x) + 1) for x, y in holes)
        return n * core.SLOT_SEC / 3600
    H = {"train": hrs(lo, B_TRAIN), "val": hrs(B_TRAIN + 1, B_VAL), "test": hrs(B_VAL + 1, hi)}
    json.dump(H, open(core.D + "/hours.json", "w")); print("hours", {k: round(v, 1) for k, v in H.items()})
    D = core.Data(); z = np.load(core.D + "/dumps.npz"); e = np.load(core.D + "/expect.npz")
    key = core.pack(D.T["mint"], D.T["slot"], D.T["idx"], D.T["j"]); kz = key[z["k"]]
    mid = {m: q for q, m in enumerate(D.mints)}
    F = json.load(open(core.D + "/live_fires.json"))
    rows = []
    for f in F:
        if "dump_slot" not in f or "buy_slot" not in f or f["mint"] not in mid: continue
        g = core.pack(mid[f["mint"]], f["dump_slot"], f["dump_idx"], f["dump_j"]); q = np.searchsorted(kz, g)
        if q >= len(kz) or kz[q] != g: continue
        sp = f["spend"] / 1e9
        def v_at(S):
            a = np.mean([e[f"L{L}_S{S}_F0.0_ev"][q] - C * e[f"L{L}_S{S}_F0.0_pf"][q] - R * (1 - e[f"L{L}_S{S}_F0.0_pf"][q]) for L in (50, 58)])
            return a
        sizes = (0.35, 0.5, 0.75, 1.0); vs = [v_at(s) for s in sizes]
        sim = float(np.interp(sp, sizes, vs))
        dly = (D.clock(np.array([f["buy_slot"]]), np.array([f["buy_idx"]]))[0] - D.clock(np.array([f["dump_slot"]]), np.array([f["dump_idx"]]))[0]) * 212.07
        rows.append(dict(slot=f["dump_slot"], sim=sim, real=f.get("chain_pnl", 0.0) if f.get("buy_ok") else f.get("chain_pnl", 0.0), ok=bool(f["buy_ok"]),
                         spend=sp, delay=float(dly), region=f["region"], run=f["run"], pf=float(np.mean([e[f"L{L}_S0.35_F0.0_pf"][q] for L in (50, 58)]))))
    print("fires matched", len(rows))
    out = {"hours": H}
    for name, sel in (("pre_test", lambda r: r["slot"] <= B_VAL), ("test", lambda r: r["slot"] > B_VAL),
                      ("train", lambda r: r["slot"] <= B_TRAIN), ("val", lambda r: B_TRAIN < r["slot"] <= B_VAL)):
        rr = [r for r in rows if sel(r)]
        if not rr: continue
        sim = np.array([r["sim"] for r in rr]); real = np.array([r["real"] for r in rr]); d = np.array([r["delay"] for r in rr])
        gap = sim - real
        bs = [np.random.default_rng(i).choice(gap, len(gap)).mean() for i in range(400)]
        okf = np.array([r["ok"] for r in rr]); pf = np.array([r["pf"] for r in rr])
        out[name] = dict(n=len(rr), sim_per_attempt_mSOL=sim.mean() * 1e3, real_per_attempt_mSOL=real.mean() * 1e3, gap_mSOL=gap.mean() * 1e3,
                         gap_p5=np.percentile(bs, 5) * 1e3, gap_p95=np.percentile(bs, 95) * 1e3, sim_fill=pf.mean(), real_fill=okf.mean(),
                         delay_ms_p25_50_75=np.percentile(d, [25, 50, 75]).tolist(), spill_share=float((d > 0).mean()),
                         mean_spend=float(np.mean([r["spend"] for r in rr])), real_total=float(real.sum()), sim_total=float(sim.sum()))
        print(name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out[name].items()})
    out["penalty_per_attempt"] = out["pre_test"]["gap_mSOL"] / 1e3 * 0.35 / out["pre_test"]["mean_spend"]
    print("FROZEN penalty per attempt at 0.35 SOL (mSOL):", round(out["penalty_per_attempt"] * 1e3, 2))
    by = collections.defaultdict(list)
    for r in rows: by[(r["region"], r["run"])].append(r["delay"])
    out["delay_by_run"] = {f"{a}:{b}": np.percentile(v, [25, 50, 75]).round(1).tolist() + [len(v)] for (a, b), v in sorted(by.items())}
    json.dump(out, open(core.D + "/calib.json", "w"), indent=1, default=float)

if __name__ == "__main__":
    main()

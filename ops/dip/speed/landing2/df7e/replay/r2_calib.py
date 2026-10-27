#!/usr/bin/env python3
# DF7e replay step 2: calibration on HIS OWN trades (counterfactual tape without his trades).
#  C1 math: my curve math at his ACTUAL buy and sell positions vs his realized net (exact wallet SOL incl. fees/tips)
#  C2 exits: his actual entries, exit by my rules (timer from his hold distribution / trail grid / fixed 10) vs C1
#  also: his landing delays (block clock, trigger -> his landed buy, filled + failed) -> his_land.npy; his holds -> his_holds.npy
import json, sys, numpy as np, collections
sys.path.insert(0, "/home/moiz/sniper/ops/dip/vm1")
import rlib, core, livecal, sim2
D = rlib.load(); T = D.T
B = json.load(open("/home/moiz/sniper-data/landing2/df7e/buys2.json"))
TRG = {r[3] * 100000 + r[4]: r for r in json.load(open(rlib.DD + "/his_triggers.json"))}
sh = T["sigh"]; o = np.argsort(sh); shs = sh[o]
def find(sig):
    h = rlib.sigh(sig); a = np.searchsorted(shs, h)
    return int(o[a]) if a < len(shs) and shs[a] == h else None
E, ours = livecal.counterfactual(D, [rlib.W])
newidx = np.cumsum(~ours) - 1
# landing delays: every attempt with a trigger (failed attempts have their own landed position s,i)
land = []
for x in B:
    r = TRG.get(x["s"] * 100000 + x["i"])
    if not r: continue
    k = r[0]
    d = sim2.clock1(D, x["s"], x["i"]) - sim2.clock1(D, int(T["slot"][k]), int(T["idx"][k]))
    if 0 < d < 5: land.append(d)
land = np.array(land); np.save(rlib.DD + "/his_land.npy", land)
print(f"his landing: n={len(land)} median {np.median(land) * 212.07:.1f} ms, p25 {np.percentile(land, 25) * 212.07:.1f}, p75 {np.percentile(land, 75) * 212.07:.1f}, p90 {np.percentile(land, 90) * 212.07:.1f}; next slot {np.mean(land >= 1):.2f}")
ours_land = np.array(json.load(open("/home/moiz/sniper-data/vm1/livecal.json"))["deltas"])
print(f"our landing: n={len(ours_land)} median {np.median(ours_land) * 212.07:.1f} ms")
holds = np.array([x["hold_slots"] for x in B if x["ok"] and x.get("hold_slots") is not None and x["hold_slots"] >= 0])
np.save(rlib.DD + "/his_holds.npy", holds)
print("his holds (slots) n", len(holds), "p10/25/50/75/90", np.percentile(holds, [10, 25, 50, 75, 90]))
# C1: his filled curve exits
rows = []
for x in B:
    if not x["ok"] or not x.get("sell_sigs") or x.get("amm") or x.get("net") is None or len(x["sell_sigs"]) != 1 or x.get("group", 1) != 1: continue
    kb = find(x["sig"]); ks = find(x["sell_sigs"][0])
    if kb is None or ks is None: continue
    r = TRG.get(x["s"] * 100000 + x["i"])
    rows.append((x, kb, ks, r[0] if r else None))
print("C1 rows", len(rows))
S2 = sim2.Sim(E, S=0.3)
fee = S2.fee
sim_pnl = []; real = []; costs = []; info = []
for x, kb, ks, kt in rows:
    m = int(T["mint"][kb]); se, ie = int(T["slot"][kb]), int(T["idx"][kb]); sx, ix = int(T["slot"][ks]), int(T["idx"][ks])
    ke = sim2.before(E, m, se, ie); kx = sim2.before(E, m, sx, ix)
    f = fee[ke]; xs = x["sol"] if x.get("sol") else 0.3e9 / (1 + f)
    Ve, Te = float(E.T["vsol"][ke]), float(E.T["vtok"][ke]); K = Ve * Te
    q = Te - K / (Ve + xs); V2 = float(E.T["vsol"][kx]) + xs
    out = (V2 - K / (K / V2 + q)) * (1 - f)
    spent = xs * (1 + f)
    c = (x["fee"] + x["tip"] + (x.get("sell_fee") or 0) + (x.get("sell_tip") or 0)) / 1e9
    sim_pnl.append((out - spent) / 1e9); real.append(x["net"] / 1e9); costs.append(c); info.append((kb, kt, se, ie, xs))
sim_pnl = np.array(sim_pnl); real = np.array(real); costs = np.array(costs)
print(f"C1 (actual positions): n={len(real)} sim-minus-costs {np.sum(sim_pnl - costs):+.3f} SOL vs realized {real.sum():+.3f} SOL; per trade {np.mean(sim_pnl - costs) * 1e3:+.2f} vs {real.mean() * 1e3:+.2f} mSOL; "
      f"abs err p50 {np.median(np.abs(sim_pnl - costs - real)) * 1e3:.2f} mSOL; corr {np.corrcoef(sim_pnl - costs, real)[0, 1]:.3f}")
# C2: his entries, my exits (same entry, same size, his costs), on the counterfactual tape
def c2(exit_spec, seeds=3):
    tot = []; hl = []
    for sd in range(seeds):
        S3 = sim2.Sim(E, S=0.3, exit=exit_spec, holds=holds, land=land, seed=sd)
        v = []
        for (x, kb, ks, kt), (kb_, kt_, se, ie, xs) in zip(rows, info):
            m = int(T["mint"][kb]); ke = sim2.before(E, m, se, ie)
            f = fee[ke]; Ve, Te = float(E.T["vsol"][ke]), float(E.T["vtok"][ke]); K = Ve * Te; q = Te - K / (Ve + xs)
            if exit_spec[0] == "timer":
                H = int(holds[S3.rng.integers(len(holds))]); sx = sim2._next_block(E, se + H); ix = int(S3.rng.random() * max(int(E.bsize(np.array([sx]))[0]), 1))
            elif exit_spec[0] == "fixed":
                sx = sim2._next_block(E, se + exit_spec[1]); ix = 0
            else:
                sx, ix = S3._exit_trail(m, se, ie, ke, xs, *exit_spec[1:])
            kx = max(sim2.before(E, m, sx, ix), ke); V2 = float(E.T["vsol"][kx]) + xs
            v.append(((V2 - K / (K / V2 + q)) * (1 - f) - xs * (1 + f)) / 1e9); hl.append(sx - se)
        tot.append(np.array(v))
    v = np.mean(tot, 0); hl = np.array(hl)
    return v, hl
print(f"his real holds on these rows p25/50/75/90: {np.percentile([x['hold_slots'] for x, *_ in rows], [25, 50, 75, 90])}")
print(f"{'exit':34s} {'sum-costs SOL':>13s} {'per trade':>9s} {'vs actual-exit sim':>18s} hold p25/50/75/90")
base = np.sum(sim_pnl - costs)
res = {}
for spec in [("timer",), ("fixed", 10), ("fixed", 30)] + [("trail", 9, tr, Q, 1500) for tr in (0.05, 0.10, 0.20) for Q in (5, 10, 30, 100)]:
    v, hl = c2(spec, 2 if spec[0] != "fixed" else 1)
    res[str(spec)] = float(np.sum(v - costs))
    print(f"{str(spec):34s} {np.sum(v - costs):+13.3f} {np.mean(v - costs) * 1e3:+9.2f} {np.sum(v - costs) - base:+18.3f} {np.percentile(hl, [25, 50, 75, 90])}", flush=True)
json.dump({"c1_sim": float(base), "c1_real": float(real.sum()), "n": len(real), "c2": res}, open(rlib.DD + "/calib_c1c2.json", "w"))

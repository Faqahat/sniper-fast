#!/usr/bin/env python3
# DF7e replay step 3: his rules at our execution on the 48 h tape (+ null, + calibration jobs). Read-only; 5 worker processes.
# Rules (causal, all info at the trigger event k):
#   D   dump        : sell >= 1 SOL that moved the price >= 6% (post vs pre), token age > 10 s
#   YD  young dump  : same, token age <= 10 s
#   WU  wake-up     : buy 0.5..4 SOL after >= 10 slots without a trade on the token, age > 10 s
#   BB  big-buy     : buy 1..8 SOL, 1..9 slots after the previous trade, age > 10 s
#   all : curve (real SOL) <= 50, normal SOL curve with its creation in the recording (core.Data universe)
#   re-entry: allowed once the previous position on that token is closed; never two positions on one token
#   exit (main) "trail": min hold 9 slots, then first others' trade >= 10% below the peak since entry, or 5 quiet slots; max 1500 slots
import sys, json, os, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/dip/vm1")
import rlib, core, livecal, sim2
OUT = rlib.DD + "/runs"; os.makedirs(OUT, exist_ok=True)
D = rlib.load(); T = D.T
ages = D.age * core.SLOT_SEC; sol = T["sol"] / 1e9
base = D.full_hist[T["mint"]] & (D.curve <= 50) & D.chain_ok
CLS = {"D": base & (T["buy"] == 0) & (sol >= 1) & (D.drop >= 0.06) & (ages > 10),
       "YD": base & (T["buy"] == 0) & (sol >= 1) & (D.drop >= 0.06) & (ages <= 10),
       "WU": base & (T["buy"] == 1) & (sol >= 0.5) & (sol <= 4) & (D.gap >= 10) & (ages > 10),
       "BB": base & (T["buy"] == 1) & (sol >= 1) & (sol <= 8) & (D.gap >= 1) & (D.gap <= 9) & (ages > 10)}
cls = np.full(len(T), -1, np.int8)
for j, (c, m) in enumerate(CLS.items()): cls[m & (cls < 0)] = j
CAND = np.where(cls >= 0)[0]
LAND = {"ours": np.array(json.load(open("/home/moiz/sniper-data/vm1/livecal.json"))["deltas"])}
MS = 1 / (core.SLOT_SEC * 1000)
for f in (16, 25, 35): LAND[f"ours-{f}ms"] = np.maximum(LAND["ours"] - f * MS, 2 * MS)
LAND["his_raw"] = np.load(rlib.DD + "/his_land.npy")
HOLDS = np.load(rlib.DD + "/his_holds.npy")
EXITS = {"trail": ("trail", 9, 0.10, 5, 1500), "fixed10": ("fixed", 10), "timer": ("timer",)}
# null: random envelope trades, same candidate count per hour bucket
env = np.where(base & (ages > 10))[0]
hb = (T["slot"].astype(np.int64) - int(T["slot"].min())) // 17000
def null_cand(seed):
    rng = np.random.default_rng(1000 + seed); out = []
    hc = np.bincount(hb[CAND]); he = hb[env]
    for h in range(len(hc)):
        pool_ = env[he == h]
        if hc[h] and len(pool_): out.append(rng.choice(pool_, min(hc[h], len(pool_)), replace=False))
    return np.concatenate(out)
# his own triggers (distinct trigger events of his attempts)
HT = np.unique([r[0] for r in json.load(open(rlib.DD + "/his_triggers.json"))])
E = None
def job(a):
    name, tape, cand_kind, land, guard, mo, ex, S, seed = a
    fn = f"{OUT}/{name}_s{seed}.npy"
    if os.path.exists(fn): return name, seed, "cached"
    t0 = time.time()
    Dx = D if tape == "full" else E
    if cand_kind == "rules": cand = CAND
    elif cand_kind == "null": cand = null_cand(seed)
    elif cand_kind == "his": cand = HT
    if tape != "full": cand = NEWIDX[cand]; cand = cand[cand >= 0]
    S_ = sim2.Sim(Dx, S=S, guard=guard, exit=EXITS[ex], holds=HOLDS, land=LAND[land], max_open=mo, seed=seed)
    rows = S_.run(cand)
    kk = cand[np.lexsort((Dx.T["idx"][cand], Dx.T["slot"][cand]))] if False else None
    # attach class + trigger slot (rows[:,0] = position in the candidate array as given)
    ci = cand[rows[:, 0].astype(np.int64)]
    if tape != "full": ci_full = OLDIDX[ci]
    else: ci_full = ci
    extra = np.stack([cls[ci_full].astype(np.float64), T["slot"][ci_full].astype(np.float64), ci_full.astype(np.float64)], 1)
    np.save(fn, np.concatenate([rows, extra], 1))
    return name, seed, f"{len(rows)} rows {time.time() - t0:.0f}s"
JOBS = []
def add(name, tape, ck, land, guard, mo, ex="trail", S=0.5, seeds=5):
    for s in range(seeds): JOBS.append((name, tape, ck, land, guard, mo, ex, S, s))
for mo in (1, 3):
    for land in ("ours", "ours-25ms", "ours-35ms"):
        add(f"main_{land}_g105_m{mo}", "full", "rules", land, 1.05, mo)
    add(f"main_ours_g118_m{mo}", "full", "rules", "ours", 1.18, mo)
    add(f"null_ours_g105_m{mo}", "full", "null", "ours", 1.05, mo)
    for ex in ("fixed10", "timer"): add(f"exit{ex}_ours_g105_m{mo}", "full", "rules", "ours", 1.05, mo, ex=ex)
add("histrig_ours_g105_m99", "full", "his", "ours", 1.05, 99)
add("histrig_ours-25ms_g105_m99", "full", "his", "ours-25ms", 1.05, 99)
# calibration (tape without him, 0.3 SOL, his guard)
for land in ("ours-16ms", "his_raw"):
    add(f"cal_rules_{land}_g118_m13", "cf", "rules", land, 1.18, 13, S=0.3, seeds=3)
    add(f"cal_rules_{land}_g118_m3", "cf", "rules", land, 1.18, 3, S=0.3, seeds=3)
    add(f"cal_histrig_{land}_g118_m99", "cf", "his", land, 1.18, 99, S=0.3, seeds=3)
if __name__ == "__main__":
    print("candidates", {c: int(m.sum()) for c, m in CLS.items()}, "distinct", len(CAND), "his triggers", len(HT), flush=True)
    E, ours = livecal.counterfactual(D, [rlib.W])
    NEWIDX = np.where(ours, -1, np.cumsum(~ours) - 1); OLDIDX = np.where(~ours)[0]
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    jobs = [j for j in JOBS if only in j[0]]
    print(len(jobs), "jobs", flush=True)
    with Pool(5) as p:
        for r in p.imap_unordered(job, jobs): print(*r, flush=True)
    print("DONE")

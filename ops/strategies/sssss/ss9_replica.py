#!/usr/bin/env python3
# sssssDdM REPLICA at OUR speed (read-only). Entry sets per day:
#  A "its":    its own entries (trigger = last non-fleet trade before each of its real buys, <= 2 slots) re-timed to our landing
#  B "model":  decision points (non-fleet trades, curve 30-113, age >= 5, >= 5 trades, we don't hold) whose selection-model
#              score (ss4_select.py, trained on R2 only) is in the top q of R2's scores
#  C "random": random decision points in the same tokens within +-300 slots of its real entries (baseline for the exit rules)
# x exit rules (timers, TP/SL, trailing, sell-on-sell variants, Haiku's exit rules from sssss/llm/exits.jsonl if present,
#   "own" = its real exit for set A is in ss5_retime.py). Landing 35 / 50 ms after the trigger, +5% guard, size = 1.88% of
#   curve capped to 0.35-0.75 SOL, follower slippage limits, sssssDdM's own trades removed from the tape for set A only.
# Costs: pump fee both sides + FIX per round trip (0.0035 = ours; also 0.00025 = its own fee level). One position at a time
# (our engine) and an unconstrained sample. Rule choice on R2, test R3, check R1 (+R4 partial).
# -> sssss/replica_<tag>.json, printed table
import sys, json, zlib, os
import numpy as np
from multiprocessing import get_context
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import gbdt_np as G
import ss8_sim as S
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
EXITS = {
    "t30": {"max_slots": 30}, "t100": {"max_slots": 100}, "t300": {"max_slots": 300}, "t900": {"max_slots": 900},
    "sl0.9_t300": {"sl": 0.9, "max_slots": 300}, "sl0.9_t900": {"sl": 0.9, "max_slots": 900}, "tp1.3_sl0.9_t900": {"tp": 1.3, "sl": 0.9, "max_slots": 900},
    "tp1.5_sl0.85_t1500": {"tp": 1.5, "sl": 0.85, "max_slots": 1500},
    "trail15_t1500": {"any_of": [[["dd", ">=", 0.15]]], "max_slots": 1500}, "trail10_sl0.92_t900": {"any_of": [[["dd", ">=", 0.10]]], "sl": 0.92, "max_slots": 900},
    "bigsell<1_t900": {"any_of": [[["ev", "==", "sell"], ["sol", ">=", 0.5], ["mult", "<", 1.0]]], "max_slots": 900},
    "bigsell<1|trail20_t1500": {"any_of": [[["ev", "==", "sell"], ["sol", ">=", 0.5], ["mult", "<", 1.0]], [["dd", ">=", 0.2]]], "max_slots": 1500},
    "sellinto_bigbuy_up|sl0.9_t1500": {"any_of": [[["ev", "==", "buy"], ["sol", ">=", 1.0], ["mult", ">=", 1.15]]], "sl": 0.9, "max_slots": 1500},
}
DAYS = ["R2", "R3", "R1", "R4"]
G_ = {}

def model_scores(d, idx):
    M = G_["M"]; FI = d["FI"]
    X = d["F"][idx][:, [FI[f] for f in M["feats"]]].astype(float)
    B = np.zeros(X.shape, np.int16)
    for c, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), X[:, c], side="right") + 1; b[np.isnan(X[:, c])] = 0; B[:, c] = b
    s = np.zeros(len(idx))
    for t in M["trees"]: s += M["lr"] * G.pred(t, B)
    return s

def setup():
    E.load(DAYS); G_["M"] = json.load(open(f"{OUT}/select_model.json"))
    rng = np.random.default_rng(7); SETS = {}
    for run in DAYS:
        d = E.DAYS[run]; F = d["F"]; FI = d["FI"]; isfleet = np.isin(d["uid"], FLEET)
        d["sibs"] = S.sib_last_sell(d)
        T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"]]
        its = []
        for t in T:
            j = t["k0"] - 1
            while j >= 0 and isfleet[j]: j -= 1
            if j >= 0 and d["tok"][j] == d["tok"][t["k0"]] and d["s"][t["k0"]] - d["s"][j] <= 2: its.append(j)
        its = np.array(sorted(set(its)), np.int64)
        base = (~isfleet) & (F[:, FI["curve"]] >= 30) & (F[:, FI["curve"]] < 113) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5)
        dp = np.flatnonzero(base); sc = model_scores(d, dp)
        # random baseline: same tokens, within +-300 slots of its entries, not one of its triggers
        near = []
        for t in T:
            a = t["k0"] - int(F[t["k0"], FI["ntr"]]) + 1; e = int(d["tend"][t["k0"]])
            cand = np.flatnonzero(base[a:e] & (np.abs(d["s"][a:e].astype(np.int64) - t["slot"]) <= 300)) + a
            if len(cand): near.append(int(rng.choice(cand)))
        SETS[run] = dict(its=its, dp=dp, sc=sc, rand=np.array(sorted(set(near)), np.int64))
        print(f"{run}: its triggers {len(its)}, decision points {len(dp)}, random {len(SETS[run]['rand'])}", flush=True)
    thr = {q: float(np.quantile(SETS["R2"]["sc"], 1 - q)) for q in (0.002, 0.005, 0.01, 0.02)}
    G_["SETS"] = SETS; G_["thr"] = thr

def task(args):
    run, setname, exname, lat, fix, mode = args
    d = E.DAYS[run]; SETS = G_["SETS"][run]
    rule = S.norm_exit(G_["EX"][exname])
    if setname == "its": ks = SETS["its"]; skip = UID
    elif setname == "rand": ks = SETS["rand"]; skip = None
    else:
        q = float(setname.split("_")[1]); ks = SETS["dp"][SETS["sc"] >= G_["thr"][q]]; skip = None
    if mode == "one": rs = S.run_entries(d, ks, lat, -0.0188, rule, fix, True, skip, d["sibs"])
    else:
        step = max(1, len(ks) // 800); rs = S.run_entries(d, ks[::step], lat, -0.0188, rule, fix, False, skip, d["sibs"])
    return args, S.stats(rs), len(ks)

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1"
    setup()
    EX = dict(EXITS)
    if os.path.exists(f"{OUT}/llm/exits.jsonl"):
        for l in open(f"{OUT}/llm/exits.jsonl"):
            o = json.loads(l)
            try: S.norm_exit(o["exit"]); EX[o["name"]] = o["exit"]
            except (ValueError, KeyError, TypeError): pass
    G_["EX"] = EX
    sets = ["its", "rand", "model_0.005", "model_0.01"]
    tasks = []
    for run in DAYS:
        for st in sets:
            for ex in EX:
                tasks.append((run, st, ex, 35, 0.0035, "unc" if st in ("its", "rand") else "one"))
                if st.startswith("model"): tasks.append((run, st, ex, 35, 0.0035, "unc"))
                if st == "its" and ex in ("t300", "t900", "sl0.9_t900", "trail15_t1500"): tasks.append((run, st, ex, 50, 0.0035, "unc"))
    res = {}
    ctx = get_context("fork")
    with ctx.Pool(int(os.environ.get("PROCS", "3"))) as p:
        for args, stt, nk in p.imap_unordered(task, tasks, chunksize=2):
            res["|".join(map(str, args))] = dict(stt, n_trig=nk)
    json.dump(dict(thr=G_["thr"], res=res, exits=EX), open(f"{OUT}/replica_{tag}.json", "w"), indent=1)
    for st in sets:
        print(f"\n=== entry set {st}")
        for ex in EX:
            line = f"  {ex:<34}"
            for run in DAYS:
                for mode in (("unc",) if st in ("its", "rand") else ("one", "unc")):
                    r = res.get(f"{run}|{st}|{ex}|35|0.0035|{mode}")
                    if r and r.get("n"): line += f" | {run} {mode} n{r['n']} {r['pnl']:+.2f} ({r['mean']:+.4f}/t, w/o top1% {r['wo_top1']:+.2f})"
            print(line, flush=True)

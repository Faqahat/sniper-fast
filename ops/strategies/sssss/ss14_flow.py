#!/usr/bin/env python3
# "SLOT-FLOW MOMENTUM" reconstruction of sssssDdM (read-only). From the measured selection model (entries driven by this
# slot's buy SOL / buy count / positive move on busy tokens) and exit hazard (sells when the price drops sharply inside the
# current slot, regardless of P&L or time held), a small family of explicit rules:
#   ENTRY: a buy trade with bsol1 >= X (buy SOL so far in this slot), nb1 >= N, move >= 0.5%, curve 37-83, >= 10 trades,
#          quiet <= 1 (+ variants with ath_r / nwal filters)
#   EXIT:  first trade where ret1 <= -Y% (price drop since the end of the previous slot), variants with ret3 / net3 / sells.
# Scored (1) as a description of ITS behaviour: entry precision / recall vs its buy attempts; exit hit rate vs its real sell
# on its own trips; (2) as OUR strategy: replay at 35 / 50 ms, +5% guard, size 1.88% of curve capped 0.35-0.75 SOL, our
# costs (FIX 0.0035; the 0.00025 column = its own fee level), one position at a time and unconstrained. Also its own entries
# (oracle) with these exits. Train R2 / test R3 / check R1 (+R4 partial).  -> sssss/flow_<tag>.json + printed table
import sys, json, zlib, os
import numpy as np
from multiprocessing import get_context
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
from ss11_rules import day_ctx, entry_score, exit_score
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
BASEW = [["move", ">=", 0.5], ["curve", ">=", 37], ["curve", "<=", 83], ["ntr", ">=", 10], ["quiet", "<=", 1]]
ENTRY = {
    "flow_b1.0_n2": {"event": "buy", "when": [["bsol1", ">=", 1.0], ["nb1", ">=", 2]] + BASEW},
    "flow_b1.5_n3": {"event": "buy", "when": [["bsol1", ">=", 1.5], ["nb1", ">=", 3]] + BASEW},
    "flow_b2.5_n3": {"event": "buy", "when": [["bsol1", ">=", 2.5], ["nb1", ">=", 3]] + BASEW},
    "flow_b1.5_n3_ath.95_nwal45": {"event": "buy", "when": [["bsol1", ">=", 1.5], ["nb1", ">=", 3], ["ath_r", "<=", 0.95], ["nwal", ">=", 45]] + BASEW},
    "flow3_b3_n4": {"event": "buy", "when": [["bsol3", ">=", 3.0], ["nb3", ">=", 4], ["bsol1", ">=", 0.8]] + BASEW},
}
EXITS = {
    "dump3": {"any_of": [[["ret1", "<=", -3]]], "max_slots": 6000},
    "dump5": {"any_of": [[["ret1", "<=", -5]]], "max_slots": 6000},
    "dump7": {"any_of": [[["ret1", "<=", -7]]], "max_slots": 6000},
    "dump5|ret3-10": {"any_of": [[["ret1", "<=", -5]], [["ret3", "<=", -10]]], "max_slots": 6000},
    "dump5|ret3-10_t900": {"any_of": [[["ret1", "<=", -5]], [["ret3", "<=", -10]]], "max_slots": 900},
    "sells2&ret1-3": {"any_of": [[["ns1", ">=", 2], ["ret1", "<=", -3]]], "max_slots": 6000},
    "net3<=-2": {"any_of": [[["net_3", "<=", -2]]], "max_slots": 6000},
    "dump5|sl0.85": {"any_of": [[["ret1", "<=", -5]]], "sl": 0.85, "max_slots": 6000},
}
DAYS = ["R2", "R3", "R1", "R4"]
G_ = {}

def setup():
    E.load(DAYS); M = E.DAYS["R2"]["M"]; SETS = {}
    for run in DAYS:
        d = E.DAYS[run]; d["sibs"] = S.sib_last_sell(d); isfleet = np.isin(d["uid"], FLEET)
        T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"]]
        its = []
        for t in T:
            j = t["k0"] - 1
            while j >= 0 and isfleet[j]: j -= 1
            if j >= 0 and d["tok"][j] == d["tok"][t["k0"]] and d["s"][t["k0"]] - d["s"][j] <= 2: its.append(j)
        SETS[run] = {"its": np.array(sorted(set(its)), np.int64)}
        for name, r in ENTRY.items():
            R = E.compile_rule(dict(r, size=0.5, exit={"max_slots": 30}), M["feats"], M["themes"], M["xl"])
            idx = E.triggers(d, R); idx = idx[~isfleet[idx]]
            SETS[run][name] = idx
        print(f"{run}: " + ", ".join(f"{k} {len(v)}" for k, v in SETS[run].items()), flush=True)
    G_["SETS"] = SETS

def task(args):
    run, st, ex, lat, mode = args
    d = E.DAYS[run]; ks = G_["SETS"][run][st]; rule = S.norm_exit(EXITS[ex]); skip = UID if st == "its" else None
    if mode == "one": rs = S.run_entries(d, ks, lat, -0.0188, rule, 0.0035, True, skip, d["sibs"])
    else:
        step = max(1, len(ks) // 800); rs = S.run_entries(d, ks[::step], lat, -0.0188, rule, 0.0035, False, skip, d["sibs"])
    o = S.stats(rs)
    if o.get("n"): o["pnl_lowfee"] = round(o["pnl"] + 0.00325 * (o["n"] - o["fail"]), 2)
    return args, o, len(ks)

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1"
    setup()
    # (1) description quality: entry precision / recall vs its attempts; exit hit rate on its own trips
    desc = {"entry": {}, "exit": {}}
    for run in ("R2", "R3"):
        ctx = day_ctx(run); d = E.DAYS[run]; M = d["M"]
        for name, r in ENTRY.items():
            R = E.compile_rule(dict(r, size=0.5, exit={"max_slots": 30}), M["feats"], M["themes"], M["xl"])
            desc["entry"].setdefault(name, {})[run] = entry_score(d, ctx, R)
        for ex, x in EXITS.items():
            desc["exit"].setdefault(ex, {})[run] = exit_score(d, run, S.norm_exit(x), ctx)
    for name, v in desc["entry"].items(): print(f"ENTRY {name:<28} " + " | ".join(f"{run} prec {v[run]['precision']:.1%} rec {v[run]['recall']:.1%} flagged {v[run]['flagged']}" for run in v), flush=True)
    for ex, v in desc["exit"].items(): print(f"EXIT  {ex:<22} " + " | ".join(f"{run} hit {v[run]['hit']:.1%} prem {v[run]['premature']:.1%} late {v[run]['late']:.1%}; its trips P&L with this exit {v[run]['pnl_rule']:+.1f} vs real {v[run]['pnl_real']:+.1f}" for run in v), flush=True)
    # (2) replay as our strategy
    tasks = []
    for run in DAYS:
        for st in ["its"] + list(ENTRY):
            for ex in EXITS:
                tasks.append((run, st, ex, 35, "unc"))
                if st != "its": tasks.append((run, st, ex, 35, "one"))
                if ex in ("dump5", "dump5|ret3-10") and st in ("its", "flow_b1.5_n3"): tasks.append((run, st, ex, 50, "unc"))
    res = {}
    with get_context("fork").Pool(int(os.environ.get("PROCS", "2"))) as p:
        for args, o, nk in p.imap_unordered(task, tasks, chunksize=1):
            res["|".join(map(str, args))] = dict(o, n_trig=nk)
    json.dump(dict(desc=desc, res=res, entry=ENTRY, exits=EXITS), open(f"{OUT}/flow_{tag}.json", "w"), indent=1)
    for st in ["its"] + list(ENTRY):
        print(f"\n=== entries {st}")
        for ex in EXITS:
            line = f"  {ex:<20}"
            for run in DAYS:
                for mode in (("unc",) if st == "its" else ("one", "unc")):
                    r = res.get(f"{run}|{st}|{ex}|35|{mode}")
                    if r and r.get("n"): line += f" | {run} {mode} n{r['n']} {r['pnl']:+.1f} ({r['mean']:+.4f}/t; lowfee {r['pnl_lowfee']:+.1f}; w/o top1% {r['wo_top1']:+.1f})"
            print(line, flush=True)

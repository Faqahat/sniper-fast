#!/usr/bin/env python3
# Replay HAIKU's refined reconstruction (round <tag>, measured by ss11_rules.py) as OUR strategy (read-only): the top entry
# rules by F1 on R2 (vs its attempts) x the top exit rules by hit rate on R2 (vs its real sells) + two fixed exits, landing
# 35 / 50 ms after the trigger, +5% guard, size 1.88% of curve capped 0.35-0.75 SOL, exit filled 35 ms after the exit
# trigger, follower slippage limits, our costs (FIX 0.0035; "lowfee" = its own ~0.0004 level). One position at a time and an
# unconstrained sample. Also its own landed entries x the same exits. R2 = train (rules were fitted on it), R3 / R1 / R4 =
# unseen.  -> sssss/haiku_replica_<tag>.json + printed table
import sys, os, json, zlib
import numpy as np
from multiprocessing import get_context
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
DAYS = ["R2", "R3", "R1", "R4"]
G_ = {}

def task(args):
    run, st, ex, lat, mode = args
    d = E.DAYS[run]; ks = G_["SETS"][run][st]; rule = S.norm_exit(G_["EX"][ex]); skip = UID if st == "its" else None
    if mode == "one": rs = S.run_entries(d, ks, lat, -0.0188, rule, 0.0035, True, skip, d["sibs"], exit_lat=35)
    else: rs = S.run_entries(d, ks[::max(1, len(ks) // 800)], lat, -0.0188, rule, 0.0035, False, skip, d["sibs"], exit_lat=35)
    o = S.stats(rs)
    if o.get("n"): o["pnl_lowfee"] = round(o["pnl"] + 0.0031 * (o["n"] - o["fail"]), 2)
    return args, o

if __name__ == "__main__":
    tag = sys.argv[1]
    rr = json.load(open(f"{OUT}/llm/rules_{tag}.json"))
    def f1(v): return 2 * v["precision"] * v["recall"] / max(1e-9, v["precision"] + v["recall"])
    ent = sorted(rr["entry"].items(), key=lambda kv: -f1(kv[1]["R2"]))[:3]
    exi = [kv for kv in sorted(rr["exit"].items(), key=lambda kv: -kv[1]["R2"]["hit"]) if "sib_sold" not in json.dumps(kv[1]["rule"])][:3]
    EX = {f"haiku_{k}": v["rule"] for k, v in exi}
    EX["dump5"] = {"any_of": [[["ret1", "<=", -5]]], "max_slots": 6000}; EX["t100"] = {"max_slots": 100}
    G_["EX"] = EX
    E.load(DAYS); M = E.DAYS["R2"]["M"]; SETS = {}
    for run in DAYS:
        d = E.DAYS[run]; d["sibs"] = S.sib_last_sell(d); isfleet = np.isin(d["uid"], FLEET)
        att = json.load(open(f"{OUT}/att_{run}.json"))
        SETS[run] = {"its": np.array(sorted({a["j"] for a in att if a["ok"] and a["dslot"] <= 2}), np.int64)}
        for k, v in ent:
            R = E.compile_rule(dict(v["rule"], size=0.5, exit={"max_slots": 30}), M["feats"], M["themes"], M["xl"])
            idx = E.triggers(d, R); SETS[run][f"haiku_{k}"] = idx[~isfleet[idx]]
        print(f"{run}: " + ", ".join(f"{k} {len(v)}" for k, v in SETS[run].items()), flush=True)
    G_["SETS"] = SETS
    tasks = []
    for run in DAYS:
        for st in SETS["R2"]:
            for ex in EX:
                tasks.append((run, st, ex, 35, "unc"))
                if st != "its": tasks.append((run, st, ex, 35, "one"))
                if ex == list(EX)[0]: tasks.append((run, st, ex, 50, "unc"))
    res = {}
    with get_context("fork").Pool(int(os.environ.get("PROCS", "3"))) as p:
        for args, o in p.imap_unordered(task, tasks, chunksize=1): res["|".join(map(str, args))] = o
    json.dump(dict(res=res, entry={k: v["rule"] for k, v in ent}, exits=EX, entry_scores={k: {r: v[r] for r in ("R2", "R3")} for k, v in ent},
                   exit_scores={k: {r: v[r] for r in ("R2", "R3")} for k, v in exi}), open(f"{OUT}/haiku_replica_{tag}.json", "w"), indent=1)
    for k, v in ent: print(f"ENTRY haiku_{k}: R2 prec {v['R2']['precision']:.1%} rec {v['R2']['recall']:.1%} | R3 prec {v['R3']['precision']:.1%} rec {v['R3']['recall']:.1%} | {json.dumps(v['rule'].get('when'))[:200]}")
    for k, v in exi: print(f"EXIT  haiku_{k}: R2 hit {v['R2']['hit']:.1%} prem {v['R2']['premature']:.1%} | R3 hit {v['R3']['hit']:.1%} prem {v['R3']['premature']:.1%}; its trips with this exit R3 {v['R3']['pnl_rule']:+.1f} vs real {v['R3']['pnl_real']:+.1f} | {json.dumps(v['rule'].get('any_of'))[:200]}")
    for st in SETS["R2"]:
        print(f"\n=== entries {st}")
        for ex in EX:
            line = f"  {ex:<24}"
            for run in DAYS:
                for mode in (("unc",) if st == "its" else ("one", "unc")):
                    r = res.get(f"{run}|{st}|{ex}|35|{mode}")
                    if r and r.get("n"): line += f" | {run} {mode} n{r['n']} {r['pnl']:+.1f} ({r['mean']:+.4f}/t; lowfee {r['pnl_lowfee']:+.1f})"
            print(line, flush=True)

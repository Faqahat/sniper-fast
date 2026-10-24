#!/usr/bin/env python3
# Is its entry edge DECISION or SPEED? Replay at our 35 ms, with fixed exits, three trigger sets per day: its LANDED buys'
# triggers, its FAILED attempts' triggers (moments it wanted but others got in first), and random same-token moments.
# Exits: timers 30 / 100 / 300 slots and the "dump5" momentum exit, with the exit filled 35 ms after the exit trigger.
# Unconstrained (every trigger). sssssDdM's own trades removed from the tape. -> printed
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
EX = {"t30": {"max_slots": 30}, "t100": {"max_slots": 100}, "t300": {"max_slots": 300}, "dump5": {"any_of": [[["ret1", "<=", -5]]], "max_slots": 6000}}
for run in sys.argv[1:] or ["R2", "R3"]:
    E.load([run]); d = E.DAYS[run]; d["sibs"] = S.sib_last_sell(d)
    att = json.load(open(f"{OUT}/att_{run}.json"))
    ok = np.array(sorted({a["j"] for a in att if a["ok"] and a["dslot"] <= 2}), np.int64)
    fl = np.array(sorted({a["j"] for a in att if not a["ok"] and a["dslot"] <= 2} - set(ok.tolist())), np.int64)
    rng = np.random.default_rng(3)
    rows = []
    for a in att[::3]:
        lo = a["q"] - int(d["F"][a["q"], d["FI"]["ntr"]]) + 1; e = int(d["tend"][a["q"]])
        c = np.flatnonzero(np.abs(d["s"][lo:e].astype(np.int64) - a["s"]) <= 300) + lo
        if len(c): rows.append(int(rng.choice(c)))
    rnd = np.array(sorted(set(rows)), np.int64)
    for name, ks in (("landed", ok), ("failed", fl), ("random", rnd)):
        ks = ks[::max(1, len(ks) // 1500)]
        line = f"{run} {name:<7} n {len(ks):5d}"
        for ex, x in EX.items():
            rs = S.run_entries(d, ks, 35, -0.0188, S.norm_exit(x), 0.0035, False, UID, d["sibs"], exit_lat=35)
            st = S.stats(rs); line += f" | {ex} {st['mean']:+.4f}/t (guard-fail {st['fail']})"
        print(line, flush=True)
    del E.DAYS[run]

#!/usr/bin/env python3
# Tight price guard as a crowd filter (read-only): ALL its buy-attempt triggers (landed + failed; the decision we could copy
# if we reproduced its rule), replayed at our 35 ms with price guards 1% / 2% / 3% / 5% vs the price right after the trigger
# (failing the guard = a failed buy, -0.0005). Exits t30 / t100 / dump5 (exit filled 35 ms after its trigger). -> printed
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
EX = {"t30": {"max_slots": 30}, "t100": {"max_slots": 100}, "dump5": {"any_of": [[["ret1", "<=", -5]]], "max_slots": 6000}}
for run in sys.argv[1:] or ["R2", "R3"]:
    E.load([run]); d = E.DAYS[run]; d["sibs"] = S.sib_last_sell(d)
    att = json.load(open(f"{OUT}/att_{run}.json"))
    ks = np.array(sorted({a["j"] for a in att if a["dslot"] <= 2}), np.int64); ks = ks[::max(1, len(ks) // 2500)]
    for g in (1.01, 1.02, 1.03, 1.05):
        S.GUARD = g
        for lat in (35, 15):
            line = f"{run} all-attempt triggers n {len(ks)} guard {g:.2f} lat {lat}"
            for ex, x in EX.items():
                rs = S.run_entries(d, ks, lat, -0.0188, S.norm_exit(x), 0.0035, False, UID, d["sibs"], exit_lat=lat)
                st = S.stats(rs); okn = st["n"] - st["fail"]
                line += f" | {ex}: filled {okn} {st['pnl']:+.1f} ({st['pnl'] / max(1, st['n']):+.4f}/try; lowfee {st['pnl'] + 0.00325 * okn:+.1f})"
            print(line, flush=True)
    del E.DAYS[run]

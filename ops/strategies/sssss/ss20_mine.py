#!/usr/bin/env python3
# My own check of the sssssDdM strategy (owner 10-24 ~22:15 PKT: "the sssssDdM strategy, can you check it yourself? replay,
# see if you can create a strategy based on it"). Two questions the study left open:
#  1. SPEED: its own entry moments, landing 15 ms (its speed) vs 35 / 50 ms (ours) after the trigger.
#  2. "CUT FAST UNLESS IT RUNS": exits that sell within 2-10 slots when the token does not follow through, and otherwise ride a
#     trailing stop for up to 2-5 min (its profit is ~45 runners/day held 1.5-2.5 min), optionally selling into a big buy.
# Entry sets: "its" = the trade right before each of its real buys (<= 2 slots, fleet trades skipped; its own trades removed
# from the tape); "flow" = Haiku's verified rule (>= 3 buys and >= 1 SOL bought in this slot, curve 37-75, >= 20 trades so far).
# Engine = ss8_sim (guard +5%, follower slippage limits, size 1.88% of curve capped 0.35-0.75 SOL, end-of-slot exit fills).
# Costs: pump fee both sides + 0.0035 SOL per round trip (ours); 0.001 shown too (one tip instead of four). R2 / R3 / R1.
import sys, json, zlib
import numpy as np
from multiprocessing import get_context
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
EXITS = {
    "timer 6 s": {"max_slots": 30},
    "cut@3sl if <+2%, else trail 12%, cap 3 min": {"any_of": [[["held", ">=", 3], ["peak", "<", 1.02]], [["dd", ">=", 0.12]]], "max_slots": 900},
    "cut@5sl if <+4%, else trail 15%, cap 3 min": {"any_of": [[["held", ">=", 5], ["peak", "<", 1.04]], [["dd", ">=", 0.15]]], "max_slots": 900},
    "cut@2sl if down, else trail 10%, cap 2 min": {"any_of": [[["held", ">=", 2], ["mult", "<", 1.0]], [["dd", ">=", 0.10]]], "max_slots": 600},
    "cut@10sl if <+8%, else trail 20%, cap 5 min": {"any_of": [[["held", ">=", 10], ["peak", "<", 1.08]], [["dd", ">=", 0.20]]], "max_slots": 1500},
    "cut@3sl if <+2%, trail 12%, sell into 1.5+ SOL buy when +30%": {"any_of": [[["held", ">=", 3], ["peak", "<", 1.02]], [["dd", ">=", 0.12]], [["ev", "==", "buy"], ["sol", ">=", 1.5], ["mult", ">=", 1.3]]], "max_slots": 900},
}
DAYS = ["R2", "R3", "R1"]; FIX = 0.0035; FIX2 = 0.001
G_ = {}

def setup():
    E.load(DAYS); SETS = {}
    for run in DAYS:
        d = E.DAYS[run]; F = d["F"]; FI = d["FI"]; isfleet = np.isin(d["uid"], FLEET)
        d["sibs"] = S.sib_last_sell(d)
        T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"]]
        its = []
        for t in T:
            j = t["k0"] - 1
            while j >= 0 and isfleet[j]: j -= 1
            if j >= 0 and d["tok"][j] == d["tok"][t["k0"]] and d["s"][t["k0"]] - d["s"][j] <= 2: its.append(j)
        cu = F[:, FI["curve"]]
        flow = np.flatnonzero((~isfleet) & (cu >= 37) & (cu <= 75) & (F[:, FI["ntr"]] >= 20) & (F[:, FI["nb1"]] >= 3) & (F[:, FI["bsol1"]] >= 1.0))
        SETS[run] = dict(its=np.array(sorted(set(its)), np.int64), flow=flow)
        print(f"{run}: its entries {len(SETS[run]['its'])}, flow-rule moments {len(flow)}", flush=True)
    G_["SETS"] = SETS

def task(a):
    run, setname, ex, lat, one = a
    d = E.DAYS[run]; ks = G_["SETS"][run][setname]
    rs = S.run_entries(d, ks, lat, -0.0188, S.norm_exit(EXITS[ex]), FIX, one, UID if setname == "its" else None, d["sibs"])
    ok = [r for r in rs if not r["fail"]]
    p = np.array([r["pnl"] for r in rs]) if rs else np.zeros(0)
    p2 = p + np.array([(FIX - FIX2) if not r["fail"] else 0.0 for r in rs]) if rs else p
    srt = np.sort(p)
    return a, dict(n=len(ok), fail=len(rs) - len(ok), pnl=float(p.sum()), pnl_lowfee=float(p2.sum()), win=float((p > 0).mean()) if len(p) else 0,
                   wo_top1=float(srt[:-max(1, len(p) // 100)].sum()) if len(p) else 0, hold=float(np.median([r["hold"] for r in ok])) if ok else 0)

if __name__ == "__main__":
    setup()
    jobs = [(r, "its", ex, lat, one) for r in DAYS for ex in EXITS for lat in (15, 35, 50) for one in (True, False)]
    jobs += [(r, "flow", ex, lat, True) for r in DAYS for ex in EXITS for lat in (35, 50)]
    res = {}
    with get_context("fork").Pool(8) as p:
        for a, v in p.imap_unordered(task, jobs): res[a] = v
    json.dump({"|".join(map(str, k)): v for k, v in res.items()}, open(f"{OUT}/mine_ss20.json", "w"))
    for setname, lats, ones in (("its", (15, 35, 50), (True, False)), ("flow", (35, 50), (True,))):
        for one in ones:
            print(f"\n=== entries: {'its own entry moments' if setname == 'its' else 'flow rule (3+ buys, 1+ SOL in slot)'} | {'one position at a time (our engine)' if one else 'all trades (many positions)'}")
            print(f"  {'exit':<58} {'land':>5} | {'R2 (train)':>22} | {'R3 (test)':>22} | {'R1 (test)':>22}")
            for ex in EXITS:
                for lat in lats:
                    cells = []
                    for r in DAYS:
                        v = res[(r, setname, ex, lat, one)]
                        cells.append(f"{v['pnl']:+7.1f} ({v['pnl_lowfee']:+6.1f}) n{v['n']:<5d}")
                    print(f"  {ex[:58]:<58} {lat:>3}ms | " + " | ".join(cells))
    print("\ncells: SOL at our fee 0.0035 per round trip (in brackets: at 0.001), n = filled trades")

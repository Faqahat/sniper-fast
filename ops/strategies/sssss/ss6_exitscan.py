#!/usr/bin/env python3
# sssssDdM EXIT anatomy (read-only). For every closed trip, walk the real tape from its entry to its sell and record, at each
# non-own trade, the position state (price multiple vs its fill after that trade, peak multiple so far, drawdown from peak,
# slots held, other-wallet sell/buy SOL since entry). The exit trigger = the last NON-FLEET trade before its sell (its sibling
# ssssswdk often sells the same token right before it: a fleet co-exit, not a trigger). Then simple exit rules are scored by
# how well they reproduce its real exit slot (first firing within +-2 slots of its sell = hit; earlier = premature):
# stop-loss levels, drawdown-from-peak levels, big-sell-while-below-entry, sell-into-big-buy-when-up, timers.
# -> sssss/exitscan_<run>.json + printed tables
import sys, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64); WDK = zlib.crc32(SIBS[0].encode())
def pct(x, ps=(10, 25, 50, 75, 90)):
    x = sorted(v for v in x if v is not None)
    return [round(x[min(len(x) - 1, int(p / 100 * len(x)))], 3) for p in ps] if x else None

def walk(d, t, isfleet):
    k0 = t["k0"]; ks = t["sells"][-1]["k"]; s0 = int(d["s"][k0]); p_in = t["p_in"]
    rows = []; pk = 1.0; ssum = bsum = 0.0
    for q in range(k0 + 1, ks):
        if d["uid"][q] == UID: continue
        m = float(d["vsol"][q] / d["vtok"][q]) / p_in; pk = max(pk, m); sol = float(d["sol"][q]) / 1e9
        fl = bool(isfleet[q])
        if not fl:
            if d["buy"][q]: bsum += sol
            else: ssum += sol
        rows.append((q, int(d["s"][q] - s0), m, pk, 1 - m / pk, bool(d["buy"][q]), sol, fl, ssum, bsum, float(d["F"][q, d["FI"]["move"]])))
    return rows

if __name__ == "__main__":
    runs = sys.argv[1:] or ["R2", "R3"]
    for run in runs:
        E.load([run]); d = E.DAYS[run]; isfleet = np.isin(d["uid"], FLEET)
        T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
        recs = []
        for t in T:
            rows = walk(d, t, isfleet)
            ks = t["sells"][-1]["k"]; sk = int(d["s"][ks]); s0 = t["slot"]
            # exit trigger: last non-fleet trade before its sell
            trg = next((r for r in reversed(rows) if not r[7]), None)
            wdk_co = any(r[7] and not r[5] and sk - (s0 + r[1]) <= 2 for r in rows[-6:])          # sibling sold <= 2 slots before
            ex_mult = t["exit_mult"]
            recs.append(dict(hold=t["hold"], pnl=t["pnl_curve"], exit_mult=ex_mult, peak=t["peak_mult"],
                             trg=dict(side="B" if trg[5] else "S", sol=round(trg[6], 3), move=round(trg[10], 2), dslot=sk - (s0 + trg[1]), m=round(trg[2], 4), pk=round(trg[3], 4), dd=round(trg[4], 4)) if trg else None,
                             wdk_co=wdk_co, n_rows=len(rows)))
            t["_rows"] = rows
        json.dump(recs, open(f"{OUT}/exitscan_{run}.json", "w"))
        print(f"\n===== {run}: {len(recs)} closed trips")
        tr = [r for r in recs if r["trg"]]
        print(f"  exit trigger (last non-fleet trade before its sell): side {collections.Counter(r['trg']['side'] for r in tr)}; dslot {collections.Counter(min(r['trg']['dslot'], 4) for r in tr).most_common()}")
        for side in "BS":
            g = [r for r in tr if r["trg"]["side"] == side]
            print(f"   {side}: sol {pct([r['trg']['sol'] for r in g])} move {pct([r['trg']['move'] for r in g])} | price mult after it {pct([r['trg']['m'] for r in g])} | peak {pct([r['trg']['pk'] for r in g])} | dd from peak {pct([r['trg']['dd'] for r in g])}")
        print(f"  sibling sold <= 2 slots before its sell: {np.mean([r['wdk_co'] for r in recs]):.0%}")
        # by outcome: losing exits vs winning exits
        for lab, f in (("exit below entry (mult<1)", lambda r: r["exit_mult"] < 1), ("exit above entry", lambda r: r["exit_mult"] >= 1)):
            g = [r for r in tr if f(r)]
            print(f"  {lab}: n {len(g)}; trigger side {collections.Counter(r['trg']['side'] for r in g)}; sell sol {pct([r['trg']['sol'] for r in g if r['trg']['side'] == 'S'])}; "
                  f"buy sol {pct([r['trg']['sol'] for r in g if r['trg']['side'] == 'B'])}; exit mult {pct([r['exit_mult'] for r in g])}; hold {pct([r['hold'] for r in g])}; dd {pct([r['trg']['dd'] for r in g])}")
        # candidate exit rules: first firing slot vs its real exit slot
        def first_fire(rows, rule):
            for r in rows:
                if r[7]: continue
                if rule(r): return r[1]
            return None
        RULES = {
            "sl 0.95": lambda r: r[2] <= 0.95, "sl 0.92": lambda r: r[2] <= 0.92, "sl 0.90": lambda r: r[2] <= 0.90, "sl 0.85": lambda r: r[2] <= 0.85,
            "dd 8%": lambda r: r[4] >= 0.08, "dd 10%": lambda r: r[4] >= 0.10, "dd 15%": lambda r: r[4] >= 0.15, "dd 20%": lambda r: r[4] >= 0.20,
            "sell>=0.5 & m<1": lambda r: (not r[5]) and r[6] >= 0.5 and r[2] < 1.0, "sell>=1 & m<1": lambda r: (not r[5]) and r[6] >= 1.0 and r[2] < 1.0,
            "sell>=0.5 any": lambda r: (not r[5]) and r[6] >= 0.5, "sell>=1 any": lambda r: (not r[5]) and r[6] >= 1.0, "sell>=2 any": lambda r: (not r[5]) and r[6] >= 2.0,
            "sell move<=-3%": lambda r: (not r[5]) and r[10] <= -3, "sell move<=-5%": lambda r: (not r[5]) and r[10] <= -5,
            "buy>=1 & m>=1.1": lambda r: r[5] and r[6] >= 1.0 and r[2] >= 1.1, "buy>=2 & m>=1.2": lambda r: r[5] and r[6] >= 2.0 and r[2] >= 1.2,
            "tp 1.3": lambda r: r[2] >= 1.3, "tp 1.5": lambda r: r[2] >= 1.5,
            "dd10% & m<1": lambda r: r[4] >= 0.10 and r[2] < 1.0, "sl0.92 | dd15%": lambda r: r[2] <= 0.92 or r[4] >= 0.15,
        }
        print("  rule: share of trips where the rule fires within +-2 slots of its real sell (hit) / fires earlier (premature) / never or later; median slots early")
        for name, rule in RULES.items():
            hit = early = late = 0; early_by = []
            for t in T:
                ff = first_fire(t["_rows"], rule)
                if ff is None or ff > t["hold"] + 2: late += 1
                elif ff < t["hold"] - 2: early += 1; early_by.append(t["hold"] - ff)
                else: hit += 1
            n = len(T)
            print(f"    {name:<18} hit {hit / n:5.1%}  premature {early / n:5.1%} (median {np.median(early_by) if early_by else 0:.0f} slots early)  never/later {late / n:5.1%}")
        del E.DAYS[run]

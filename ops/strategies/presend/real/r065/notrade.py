#!/usr/bin/env python3
"""REPLAY_065, HINDSIGHT: fills where no other wallet traded the token between our buy and our sell (chain tape, strictly between
the two positions). Their P&L live (MEASURED) and at 0.65 (INFERRED), and each run's total without them. Then one cheap check of
an at-entry signal: the token's trade count in the 10 slots before the trigger (pre-send) / before the dump (regular).
Writes /home/moiz/sniper-data/replay065/notrade.json"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core

RENT_BACK = 1_508_820 / 1e9


def main():
    D = core.Data()
    PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
    R = json.load(open(f"{core.BASE}/results.json"))
    rep = {(t["run"], t["kind"], t["seg"], t["mint"], tuple(t["buy_pos"])): t for t in R["trades"]}
    out = {}
    rows = []
    for p in PS + RG:
        t = rep[(p.run, p.kind, p.seg, p.mint, p.buy_pos)]
        nb = sum(1 for r in p.rows if r["kind"] == "trade" and (r["s"], r["i"]) < p.sell_pos)
        if p.kind == "ps": s0 = p.trig["slot"]
        else: s0 = p.dump["s"] if p.dump else p.buy_pos[0]
        pre10 = sum(1 for x in D.tape[p.mint]["trades"] if s0 - 10 <= x["s"] < s0)
        # wallet-level (rent back for pre-send fills)
        rb = RENT_BACK if p.kind == "ps" else 0.0
        rows.append(dict(run=p.run, kind=p.kind, mint=p.mint, nb=nb, pre10=pre10, live=t["live"] + rb, s65=(t["s65"] or 0) + rb, why=p.exit_why))
    for run in ("r24", "r25"):
        for kind in ("ps", "reg"):
            Q = [x for x in rows if x["run"] == run and x["kind"] == kind]
            Z = [x for x in Q if x["nb"] == 0]
            o = dict(n=len(Q), n_zero=len(Z), zero_live=sum(x["live"] for x in Z), zero_65=sum(x["s65"] for x in Z),
                     tot_live=sum(x["live"] for x in Q), tot_65=sum(x["s65"] for x in Q),
                     tot_live_wo=sum(x["live"] for x in Q if x["nb"] > 0), tot_65_wo=sum(x["s65"] for x in Q if x["nb"] > 0),
                     zero_exits=dict(collections.Counter(x["why"] for x in Z)))
            out[f"{run}:{kind}"] = o
            print(run, kind, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in o.items()})
    # the at-entry signal (pre-send, both runs): trade count in the 10 slots before the trigger
    P = [x for x in rows if x["kind"] == "ps"]
    z = np.array([x["pre10"] for x in P if x["nb"] == 0]); nz = np.array([x["pre10"] for x in P if x["nb"] > 0])
    sig = dict(zero_pcts=np.percentile(z, [25, 50, 75]).tolist() if len(z) else None, other_pcts=np.percentile(nz, [25, 50, 75]).tolist())
    rules = []
    for thr in (2, 4, 6, 8, 10, 15, 20):
        sk = [x for x in P if x["pre10"] < thr]
        rules.append(dict(thr=thr, skipped=len(sk), skipped_zero=sum(1 for x in sk if x["nb"] == 0), skipped_live=sum(x["live"] for x in sk), skipped_65=sum(x["s65"] for x in sk)))
    sig["rules"] = rules
    out["signal_pre10"] = sig
    print("pre-send trades in the 10 slots before the trigger: no-trade fills p25/50/75", sig["zero_pcts"], "| others", sig["other_pcts"])
    for r in rules: print("   skip if <", r["thr"], {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    json.dump(out, open(f"{core.BASE}/notrade.json", "w"), indent=1)


if __name__ == "__main__":
    main()

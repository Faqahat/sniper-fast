#!/usr/bin/env python3
"""REPLAY_065: the engine's PAPER pre-send next to live, on the same basis.
  paper   : the shadow's own fills (rows a / b / c = landing 0 / 5 / 10 ms after the crossing trade), re-computed with its own
            model (paper.py, checked exact against every logged 0.55 SOL paper exit) at 0.34 and 0.65 SOL, with LIVE per-fill
            costs (buy fee 5,120 + tip 200,000 + sell fee 605,000 + sell tips 1,200,000 + token-account close fee 5,020
            lamports; the rent comes back) and no failed tries; only windows armed while live pre-send was on (each segment's
            start to its presend_live_stop)
  live    : realized + rent back per fill (MEASURED); 0.65 = the chain replay (run065 results, INFERRED)
  (a) all paper fills vs all live fills; (b) windows both filled, per fill
Writes /home/moiz/sniper-data/replay065/paper.json"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core, paper

COST = (5120 + 200_000 + 605_000 + 1_200_000 + 5020) / 1e9
RENT_BACK = 1_508_820 / 1e9


def main():
    D = core.Data()
    PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
    R = json.load(open(f"{core.BASE}/results.json"))
    rep65 = {(t["run"], t["seg"], t["mint"], tuple(t["buy_pos"])): t for t in R["trades"] if t["kind"] == "ps"}
    out = {}
    for run, X in D.live.items():
        spans = {}
        for s in X["segs"]:
            st = next((x for x in X["stops"] if x["seg"] == s["seg"]), None)
            spans[s["seg"]] = (s["t"], st["t"] if st else 1 << 62, s["ps_spend"])
        arms = X["sh_arm"]
        fills = {(f["seg"], f["w"], f["row"]): f for f in X["sh_fill"]}
        live_arm = {}
        for (seg, w), W in X["ps"].items():
            tr = W["arm"]["trig"]; live_arm[(seg, tr["mint"], tr["slot"], tr["idx"])] = W
        skipped = {}
        for r in X["skips"]:
            tr = r["trig"]; skipped[(r["seg"], tr["mint"], tr["slot"], tr["idx"])] = r["why"]
        our_sigs = set()
        for W in X["ps"].values():
            for f in W["fills"]: our_sigs.add(f["sig"])
            for s in W["sells"]: our_sigs.add(s["sig"])
        rows = []
        for e in X["sh_exit"]:
            seg = e["seg"]; f = fills.get((seg, e["w"], e["row"]))
            a = arms.get((seg, e["w"]))
            if f is None or a is None: continue
            t0, t1, _ = spans[seg]
            if not (t0 <= a["t"] <= t1): continue
            tr = D.tape[f["mint"]]["trades"]; m = f["m"]
            k = next((q for q, t in enumerate(tr) if (t["s"], t["i"], t["j"]) == (m["slot"], m["idx"], m["j"])), None)
            if k is None: continue
            v = {}
            for sz in (0.55, 0.34, 0.65):
                r = paper.path(tr, k, f["a_land"], sz)
                v[sz] = None if r is None else r["val"]
            r34x = paper.path(tr, k, f["a_land"], 0.34, skip_sigs=our_sigs)
            key = (seg, f["mint"], a["slot"], a["idx"])
            W = live_arm.get(key)
            lf = None
            if W is not None and W["fills"]:
                lf = W["fills"][0]
            rows.append(dict(seg=seg, row=e["row"], mint=f["mint"], age=a.get("age_slots"), logged055=e["pnl"], logged_net_cheap=e["net_cheap"], v055=v[0.55],
                             v034=v[0.34], v065=v[0.65], v034_noours=None if r34x is None else r34x["val"],
                             live_armed=W is not None, live_skip=skipped.get(key), live_filled=lf is not None,
                             live_key=(run, seg, lf["mint"], (lf["slot"], lf["idx"])) if lf else None))
        # live side
        P = [p for p in PS if p.run == run]
        live = dict(fills=len(P), wins=sum(1 for p in P if p.realized > 0), net034=sum(p.realized / 1e9 + RENT_BACK for p in P),
                    net065=sum((rep65[(p.run, p.seg, p.mint, p.buy_pos)]["s65"] or 0) + RENT_BACK for p in P))
        res = dict(live=live, rows=rows)
        for rw in ("a", "b", "c"):
            Q = [x for x in rows if x["row"] == rw and x["v034"] is not None]
            res[f"paper_{rw}"] = dict(fills=len(Q), wins034=sum(1 for x in Q if x["v034"] - COST > 0), net034=sum(x["v034"] - COST for x in Q), net065=sum(x["v065"] - COST for x in Q),
                                      logged055_net_cheap=sum(x["logged_net_cheap"] for x in Q), create_slot=sum(1 for x in Q if x["age"] == 0),
                                      create_slot_net034=sum(x["v034"] - COST for x in Q if x["age"] == 0),
                                      live_skipped=collections.Counter(x["live_skip"] for x in Q if x["live_skip"]), not_armed_live=sum(1 for x in Q if not x["live_armed"]))
            # (b) windows both filled
            B = [x for x in Q if x["live_filled"]]
            lv034 = []; lv065 = []
            for x in B:
                run_, seg_, mint_, bp = x["live_key"]
                p = next(p for p in P if p.seg == seg_ and p.mint == mint_ and p.buy_pos == bp)
                lv034.append(p.realized / 1e9 + RENT_BACK); lv065.append((rep65[(run_, seg_, mint_, bp)]["s65"] or 0) + RENT_BACK)
            res[f"shared_{rw}"] = dict(n=len(B), paper034=sum(x["v034"] - COST for x in B), live034=sum(lv034), paper065=sum(x["v065"] - COST for x in B), live065=sum(lv065),
                                       paper034_noours=sum((x["v034_noours"] or 0) - COST for x in B))
        out[run] = res
        print(run, "live", {k: round(v, 4) if isinstance(v, float) else v for k, v in live.items()})
        for rw in ("a", "b", "c"):
            print("  paper", rw, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res[f"paper_{rw}"].items()})
            print("  shared", rw, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res[f"shared_{rw}"].items()})
    for run in out:
        for x in out[run]["rows"]: x.pop("live_key", None)
    json.dump(out, open(f"{core.BASE}/paper.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

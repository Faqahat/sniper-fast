#!/usr/bin/env python3
"""TAIL t5: score candidate guards (predicate on signing-time features) on DEV / VAL real fills."""
import sys, pickle, collections
T = "/home/moiz/sniper-data/filters3/tail"
HOURS = {"r37": 18.4, "r38": 1.6, "r39": 3.1, "r40": 17.3, "r41": 1.3, "r42a": 32.13, "r42b": 20.58}
ANN = ["r39", "r40", "r41", "r42a"]
rows = pickle.load(open(f"{T}/eval_rows.pkl", "rb"))
ATT0, ATT1 = 1793590000e9, 1793597000e9  # filled below from data: the 11-02 attack window (record clock 08:29..08:36 PKT)
def score(name, pred, need_ann=True, seq=None, show=True):
    out = {}
    blocked = {}
    if seq:  # sequential rule (breaker): sees only trades it let through
        state = seq()
        for r in rows:
            b = state.decide(r)
            blocked[id(r)] = b
            if not b: state.taken(r)
    for st in ("DEV", "VAL"):
        R = [r for r in rows if r["set"] == st and (not need_ann or r["F"].get("has_ann"))]
        B = [r for r in R if (blocked[id(r)] if seq else pred(r["F"], r))]
        hrs = sum(HOURS[k] for k in {r["rk"] for r in R})
        saved = -sum(r["pnl"] for r in B)
        w = [r["pnl"] for r in B if r["pnl"] > 0]; l = [r["pnl"] for r in B if r["pnl"] <= 0]
        bs = sorted(r["pnl"] for r in B)
        perrun = collections.defaultdict(lambda: [0, 0.0])
        for r in B: perrun[r["rk"]][0] += 1; perrun[r["rk"]][1] -= r["pnl"]
        base = sum(r["pnl"] for r in R)
        out[st] = dict(n=len(B), of=len(R), saved=saved, day=saved / hrs * 24, w=(len(w), sum(w)), l=(len(l), sum(l)), wo5=-sum(bs[5:]), perrun=dict(perrun), base=base, hrs=hrs,
                       runs_pos=sum(1 for k in {r['rk'] for r in R} if perrun.get(k, [0, 0])[1] > 0.0005), runs_neg=sum(1 for k in {r['rk'] for r in R} if perrun.get(k, [0, 0])[1] < -0.0005))
    if show:
        s = f"{name:44s}"
        for st in ("DEV", "VAL"):
            o = out[st]
            s += f" | {st} blk {o['n']:3d}/{o['of']} save {o['saved']:+6.2f} ({o['day']:+5.2f}/d) win {o['w'][0]}/{o['w'][1]:+.2f} los {o['l'][0]}/{o['l'][1]:+.2f} w/o5 {o['wo5']:+5.2f}"
        s += " | runs " + " ".join(f"{k}:{v[0]}/{v[1]:+.2f}" for k, v in sorted(out['DEV']['perrun'].items()))
        print(s)
    return out
if __name__ == "__main__":
    for st in ("DEV", "VAL"):
        R = [r for r in rows if r["set"] == st]; Ra = [r for r in R if r["F"].get("has_ann")]
        print(st, "all", len(R), f"{sum(r['pnl'] for r in R):+.3f}", "| with holders", len(Ra), f"{sum(r['pnl'] for r in Ra):+.3f}")
    g = lambda k, x: (lambda F, r: (F.get(k) or 0) >= x)
    for k, xs in [("n_oth6", [2, 3, 4]), ("sum_oth", [25, 30, 35, 40, 50]), ("samage", [15, 20, 25, 30]), ("bundle", [15, 20, 25, 30, 35]),
                  ("sum_fresh", [20, 25, 30, 35]), ("max_oth", [12, 15, 20]), ("ob6", [12, 15, 20]), ("risky_sum", [6, 10, 15]),
                  ("led_dump_n", [1, 2, 3, 5]), ("led_dump_bad", [1, 2, 3]), ("led_dump_oth_bad", [1, 2, 3]), ("led_dump24_bad", [1, 2, 3]),
                  ("led_whale_dumpbad", [1, 2]), ("led_whale_bad", [1, 2, 3]), ("led_cr_bad", [1, 2])]:
        for x in xs: score(f"{k}>={x}", g(k, x))
    score("led_whale_pnl<=-0.1", lambda F, r: F["led_whale_pnl"] <= -0.1)
    score("led_cr_pnl<=-0.1", lambda F, r: F["led_cr_pnl"] <= -0.1)
    score("led_dump_pnl<=-0.1", lambda F, r: F["led_dump_pnl"] <= -0.1)
    score("led_dump_pnl<=-0.2", lambda F, r: F["led_dump_pnl"] <= -0.2)

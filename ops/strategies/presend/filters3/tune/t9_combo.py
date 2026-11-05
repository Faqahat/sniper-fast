#!/usr/bin/env python3
"""TUNE t9: the next build's LIVE set, simulated in order on kept trades only (a blocked trade never feeds a ledger / the breaker):
G1 (planned: creator ledger sum <= -0.10, n >= 1) vs G1' (this study: n >= 2, sum <= -0.05; both carried across runs, any creator holding),
QUIET3-B (strict in-hold follow label), breaker 2:0.2:10:30 (loss known at fill t + 5 s). Realized P&L saved per segment, w/o top 5."""
import sys, pickle, collections, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/moiz/sniper-data/filters3/tune/pos_all.pkl", "rb"))
A0, A1 = 1793590164e9 - 60e9, 1793590555e9 + 60e9
for r in P:
    r["attk"] = r["run"] == "r42" and A0 <= r["t"] <= A1
    a = T.load(r["run"])["arms"].get(r["k"], {}); r["arm_seq"] = a.get("_seq", r["seq"]); r["arm_t"] = (a.get("trig") or a.get("dump") or {}).get("t") or r["t"]
    r["creator"] = (a.get("ann") or {}).get("creator")
SEG = {"DEV": lambda r: r["per"] == "DEV" and r["run"] not in ("r37", "r38"), "VALx": lambda r: r["per"] == "VAL" and not r["attk"],
       "VAL": lambda r: r["per"] == "VAL", "HOLD": lambda r: r["per"] == "HOLD"}
H = {"DEV": 53.87, "VALx": 19.93, "VAL": 20.6, "HOLD": 14.23}
def sim(g1=None, b=False, brk=False):
    blocked = {}; led = collections.defaultdict(list); losses = []; pause_until = 0
    for run in T.RUNS:
        R = [r for r in P if r["run"] == run]
        evs = sorted([(r["arm_seq"], 0, i) for i, r in enumerate(R)] + [(r["seq"], 1, i) for i, r in enumerate(R)])
        for s, typ, i in evs:
            r = R[i]; key = (run, r["k"])
            if typ == 0:
                why = []
                h = led[r["creator"]] if r["creator"] else []
                if g1 and len(h) >= g1[0] and sum(x[1] for x in h) <= g1[1]: why.append("G1")
                if b:
                    hh = [x for x in h if x[0] >= r["arm_t"] - 24 * 3.6e12][-3:]
                    if hh and not any(x[2] for x in hh): why.append("B")
                if brk and r["arm_t"] < pause_until: why.append("BRK")
                if why: blocked[key] = why
            elif key not in blocked:
                if r["creator"]: led[r["creator"]].append((r["t"], r["pnl"], r["followed"]))
                if brk and r["pnl"] <= -0.2:
                    tk = r["t"] + 5e9; losses = [x for x in losses if x >= tk - 600e9] + [tk]
                    if len(losses) >= 2: pause_until = tk + 1800e9; losses = []
    return blocked
out = {}
for name, kw in (("G1 planned (n>=1, <=-0.10)", dict(g1=(1, -0.10))), ("G1' (n>=2, <=-0.05)", dict(g1=(2, -0.05))),
                 ("QUIET3-B alone", dict(b=True)), ("breaker alone", dict(brk=True)),
                 ("planned live: B + G1 + breaker", dict(g1=(1, -0.10), b=True, brk=True)),
                 ("G1' + breaker", dict(g1=(2, -0.05), brk=True)), ("G1' + B + breaker", dict(g1=(2, -0.05), b=True, brk=True))):
    B = sim(**kw); row = {}
    s = f"{name:32s}"
    for sn, sf in SEG.items():
        v = [r["pnl"] for r in P if sf(r) and (r["run"], r["k"]) in B]; d = T.summ(v); d["wo5"] = T.wo_top(v); d["day"] = round(d["saved"] / H[sn] * 24, 2); row[sn] = d
        s += f" | {sn} {d['n']:3d} p{(d['prec'] or 0):.2f} {d['saved']:+6.3f} ({d['day']:+5.2f}/d) w5 {d['wo5']:+6.3f}"
    hr = {run: round(-sum(r["pnl"] for r in P if r["run"] == run and (r["run"], r["k"]) in B), 3) for run in ("r43", "r44", "r45", "r46")}
    print(s + f" | HOLD by run {hr}"); out[name] = dict(row, hold_runs=hr)
json.dump(out, open("/home/moiz/sniper-data/filters3/tune/t9_combo.json", "w"), indent=1)

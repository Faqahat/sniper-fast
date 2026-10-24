#!/usr/bin/env python3
# REPLICA of BUkpShoE at OUR speed (read-only). Entry = decision points (other-wallet trades on curve 30-50 SOL, age >= 5,
# >= 5 trades) whose selection-model score (bk3_select.py, trained on R2 only) is in the top q of R2's points; size 0.6 SOL
# (its 2%-of-curve rule at curve 30 is ~0.6; inside our 0.35-0.75 cap); landing 35 / 50 ms after the trigger, +5% guard,
# follower slippage limits, our costs (patterns/p4_eval.py sim/evaluate). Exit rules: its 300 s timeout, sell-on-sell
# variants, TP/SL, and Haiku's hypotheses (bukp/llm/answers_*.jsonl). Threshold + exit chosen on R2, tested on R3, checked
# on R1 (+R4 partial). One position at a time (our engine) and unconstrained (its style: many positions at once).
# -> bukp/replica.json
import sys, json, zlib, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp")
import p4_eval as E
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/bukp"
W = "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP"; UID = zlib.crc32(W.encode())
MD = json.load(open(f"{OUT}/select_model.json"))

def scores(d, idx):
    FI = d["FI"]; X = d["F"][idx][:, [FI[f] for f in MD["feats"]]].astype(float)
    B = np.zeros(X.shape, np.int16)
    for c, e in enumerate(MD["edges"]):
        b = np.searchsorted(np.array(e), X[:, c], side="right") + 1; b[np.isnan(X[:, c])] = 0; B[:, c] = b
    s = np.zeros(len(idx))
    for t in MD["trees"]: s += MD["lr"] * G.pred(t, B)
    return s

def points(d, cmax=50.0):
    F = d["F"]; FI = d["FI"]
    m = (d["uid"] != UID) & (F[:, FI["curve"]] >= 30) & (F[:, FI["curve"]] < cmax) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5)
    return np.flatnonzero(m)

EXITS = {
    "timeout300": dict(max_slots=1417),
    "timeout300+bigsell": dict(max_slots=1417, on=["big_sell"]),
    "timeout60+bigsell": dict(max_slots=283, on=["big_sell"]),
    "tp1.2_sl0.85_t300": dict(tp=1.2, sl=0.85, max_slots=1417),
    "tp1.15_sl0.9_t150": dict(tp=1.15, sl=0.9, max_slots=708),
    "tp1.1_sl0.93_t60": dict(tp=1.1, sl=0.93, max_slots=283),
    "t30": dict(max_slots=141),
}

def rule(name, ex, size=0.6):
    return dict(name=name, event="any", idle=0, mode="follow", race=True, size=size, tp=ex.get("tp"), sl=ex.get("sl"), max_slots=ex["max_slots"],
                on=sorted(ex.get("on", [])), conds=[], special=[], sig=name)

if __name__ == "__main__":
    days = ["R2", "R3", "R1", "R4"]
    E.load(days)
    extra = {}
    try:
        for l in open(f"{OUT}/llm/exits_haiku.jsonl"):
            o = json.loads(l); extra[o["name"]] = o["exit"]
    except FileNotFoundError: pass
    EX = {**EXITS, **extra}
    S = {}
    for run in days:
        d = E.DAYS[run]; idx = points(d); s = scores(d, idx); S[run] = (idx, s)
        print(f"{run}: {len(idx)} decision points (curve 30-50)", flush=True)
    thr = {q: float(np.quantile(S["R2"][1], 1 - q)) for q in (0.002, 0.005, 0.01, 0.02)}
    res = {}
    for q, th in thr.items():
        for exn, ex in EX.items():
            R = rule(f"q{q}_{exn}", ex)
            for run in days:
                idx, s = S[run]; sel = idx[s >= th]
                for lat in (35, 50):
                    r = E.evaluate(E.DAYS[run], R, lat, sel, unc_cap=4000)
                    res[f"{R['name']}|{run}|{lat}"] = {k: v for k, v in r.items() if k not in ("ks", "pnls")}
            r2 = res[f"{R['name']}|R2|35"]; r3 = res[f"{R['name']}|R3|35"]; r1 = res[f"{R['name']}|R1|35"]
            print(f"top {q:.1%} {exn:<22} R2 n {r2.get('n', 0):5d} pnl {r2.get('pnl', 0):+7.2f} mean {r2.get('mean', 0):+.4f} | R3 n {r3.get('n', 0):5d} pnl {r3.get('pnl', 0):+7.2f} mean {r3.get('mean', 0):+.4f} | R1 pnl {r1.get('pnl', 0):+7.2f} mean {r1.get('mean', 0):+.4f}"
                  f" || unconstrained mean R2 {r2.get('u_mean', 0):+.4f} R3 {r3.get('u_mean', 0):+.4f} R1 {r1.get('u_mean', 0):+.4f} (trig/day R2 {r2.get('trig')})", flush=True)
    json.dump(dict(thr=thr, res=res), open(f"{OUT}/replica.json", "w"))

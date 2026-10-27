#!/usr/bin/env python3
"""HAQQ_MODEL step 4 (read-only, offline): regular dip buys (M2 gate) at 0.55 SOL on the held-out 24 h, as haqq_sel/h4_m2.py
(the study's dump rows, M2 >= the live threshold inside the envelope, exit c4, dd_lib.sim engine limits, AMS main / FRA+AMS aside),
with rows from m0_m2build55.py (DD_SIZE 0.55). Sets: ALL, HQ (haqq's tokens, hindsight), HQKNOWN (haqq traded before the dump slot),
MODEL80 / MODEL85 (score at +14 slots >= the val-recall-80% / 85% threshold, dump slot >= create slot + 14), MODEL80_N0.
Then the scenario tables (haqq_sel/h6_m2_tables.py logic: 35 ms row = ideal, 50%/30% landing on the 35 ms fills, 50/75 ms rows).
Out: DATA/m2_rows.pkl, DATA/m2_tables.json"""
import sys, os, json, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_model")
import dd_lib as L
import dd20_shadow_eval as D20
from m2_presend import picks
DATA = "/home/moiz/sniper-data/haqq_model"; HQS = "/home/moiz/sniper-data/haqq_sel"
W0 = 1793038500; W1 = 1793124900
E4 = L.EXI["c4_tpnone_slnone"]
BUNDLE = f"{L.OUT}/m2_v3_reg4_top25.json"
FAIL = 0.0005; NB = 4000
rng = np.random.default_rng(5)


def boot(vals, p=None, fills=None):
    vals = np.asarray(vals, float); n = len(vals)
    if n == 0: return 0.0, 0.0, 0.0
    tot = []
    for _ in range(NB):
        ix = rng.integers(0, n, n)
        if p is None: tot.append(vals[ix].sum())
        else:
            f = fills[ix]; land = f & (rng.random(n) < p); tot.append(np.where(land, vals[ix], -FAIL).sum())
    tot = np.array(tot)
    return float(np.percentile(tot, 5)), float(np.percentile(tot, 95)), float((tot > 0).mean())


if __name__ == "__main__":
    d = D20.load_dd1(f"{DATA}/m2/dd1_HQ.npz", W0, W1)
    meta = json.load(open(f"{HQS}/m2/work/day_HQ_meta.json"))["meta"]
    mint = np.array([meta[t]["m"] for t in d["tok"]])
    B0 = json.load(open(BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
    P, B = D20.bundle_scores(BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
    HQ = {x["mint"]: x for x in json.load(open(f"{HQS}/tokens.json"))["tokens"]}
    hq = np.array([m in HQ for m in mint])
    known = np.array([(m in HQ) and HQ[m]["first_slot"] < s_ for m, s_ in zip(mint, d["s"])])
    P80, _, _ = picks(14, 0.80); P85, _, _ = picks(14, 0.85); P80n0, _, _ = picks(0, 0.80)
    pk = lambda PP: np.array([(m in PP) and s_ >= PP[m] for m, s_ in zip(mint, d["s"])])
    sel = d["env"] & (P >= MIN)
    sets = dict(ALL=sel, HQ=sel & hq, HQKNOWN=sel & known, MODEL80=sel & pk(P80), MODEL85=sel & pk(P85), MODEL80_N0=sel & pk(P80n0))
    print(f"rows {len(mint)}, M2 picks {int(sel.sum())}: " + ", ".join(f"{k} {int(v.sum())}" for k, v in sets.items()))
    out = dict(MIN=MIN); tables = {}
    for nm, m_ in sets.items():
        for srv in (("a",), ("f", "a")):
            res = {}
            for lat in (35, 50, 75):
                o = L.sim(d, m_, (35, 50, 75).index(lat), E4, servers=srv, detail=True)
                rows = [(int(r), sv, float(p), int(f)) for r, sv, p, f in o["rows"]]
                out[(nm, "+".join(srv), lat)] = dict(att=o["att"], fill=o["fill"], fail=o["fail"], pnl=o["pnl"], rows=rows)
                v = np.array([p for _, _, p, f in rows]); f = np.array([bool(f) for _, _, p, f in rows])
                lo, hi, pos = boot(v)
                res[f"l{lat}"] = dict(att=o["att"], fills=int(f.sum()), pnl=float(v.sum()), lo=lo, hi=hi, pos=pos, per_fill=float(v[f].mean()) if f.any() else 0.0)
                if lat == 35:
                    for lab, p in (("p50", 0.5), ("p30", 0.3)):
                        exp = float((v * f).sum() * p + (-FAIL) * (f.sum() * (1 - p) + (~f).sum()))
                        lo, hi, pos = boot(v, p, f); res[lab] = dict(fills=float(f.sum() * p), pnl=exp, lo=lo, hi=hi, pos=pos)
            tables[f"{nm}|{'+'.join(srv)}"] = res
            r = res
            print(f"{nm:10s} {'+'.join(srv):3s} | ideal(35) {r['l35']['pnl']:+.2f} ({r['l35']['fills']} fills) | 50% {r['p50']['pnl']:+.2f} | 30% {r['p30']['pnl']:+.2f} "
                  f"| 50ms {r['l50']['pnl']:+.2f} ({r['l50']['fills']}) [{r['l50']['lo']:+.2f},{r['l50']['hi']:+.2f}] | 75ms {r['l75']['pnl']:+.2f} ({r['l75']['fills']})", flush=True)
    pickle.dump(out, open(f"{DATA}/m2_rows.pkl", "wb"))
    json.dump(tables, open(f"{DATA}/m2_tables.json", "w"), indent=1)

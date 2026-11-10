#!/usr/bin/env python3
"""MIN-AGE: the REPLAY's re-arm fills (rule R0) by the dump's token age, per run (INFERRED; the tape is MEASURED): fills and cash per
age bucket (per rep), and who sold into the model's hold (between our model buy's landing and our model sell's landing), by role
(creator / dumper / holder >= 6% at the check / create_slot buyer / early buyer within create + 3 slots / other).
usage: ma13_model_young.py RUNDIR CTX.pkl OUT.json [--variant R0]"""
import sys, glob, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
import ma_lib as M
from ma11_young import bucket


def main(rundir, ctxp, outp, variant="R0"):
    ctx = pickle.load(open(ctxp, "rb")); tape = M.Tape(ctx["tab"])
    files = sorted(glob.glob(f"{rundir}/{variant}__*.pkl"))
    reps = len(files)
    agg = collections.defaultdict(lambda: collections.defaultdict(float)); cache = {}
    for f in files:
        rows = pickle.load(open(f, "rb"))["rows"]
        for r in rows:
            if r["kind"] != "rearm" or not r["filled"]: continue
            k = tuple(r["key"])
            if len(k) != 4 or k[1] == "chain": continue
            m, ds, di, dj = k
            if m not in cache:
                t = tape.trades(m); c = tape.creates.get(m) or {}
                if t is None or c.get("slot") is None: cache[m] = None; continue
                s0 = c["slot"]; ids = tape.ids
                creator = {c.get("creator"), c.get("user"), c.get("payer")} - {None}
                first_buy = {}; cs = set()
                for x in t:
                    u = ids[int(x["user"])]
                    if x["buy"] and u not in first_buy: first_buy[u] = int(x["slot"])
                    if x["buy"] and int(x["slot"]) == s0 and u not in creator: cs.add(u)
                cache[m] = (t, s0, creator, first_buy, cs)
            if cache[m] is None: continue
            t, s0, creator, first_buy, cs = cache[m]
            ids = tape.ids
            dumper = next((ids[int(x["user"])] for x in t if (int(x["slot"]), int(x["idx"]), int(x["j"])) == (ds, di, dj)), None)
            tl = tape.tok(m)
            cs_slot = tape.slot_ge(ds + M.WAIT)
            holders = {w for w, p in tl.holders_before_slot(cs_slot, 6, tape)} if cs_slot else set()
            def role(u):
                if u in creator: return "creator"
                if u == dumper: return "dumper"
                if u in holders: return "holder"
                if u in cs: return "create_slot"
                if first_buy.get(u, 10 ** 12) <= s0 + 3: return "early"
                return "other"
            b = bucket(ds - s0)
            buy_pos = (r["fs"], r["fi"])
            # the model sell's landing on the block clock: the fill's landing + (sell landing seen - fill seen) (c_sell when saved)
            c_sell = r.get("c_sell") or (tape.cc(r["fs"], r["fi"]) + (r["t_close"] - ctx["R"]["C"] - r["t_fill"]))
            sold = collections.defaultdict(float)
            for x in t:
                p = (int(x["slot"]), int(x["idx"]))
                if p < buy_pos: continue
                if tape.cc(p[0], p[1]) >= c_sell: break
                u = ids[int(x["user"])]
                if u in M.OURS or x["buy"]: continue
                sold[role(u)] += x["sol"] / 1e9
            for key in (b, "<=10 all" if ds - s0 <= 10 else ">10 all", "all"):
                A = agg[key]
                A["fills"] += 1 / reps; A["cash"] += r["cash"] / reps; A["cash_cut"] += r["cash_cut"] / reps; A["wins"] += (r["cash"] > 0) / reps
                for k2, v in sold.items(): A["sold_" + k2] += v / reps
                for k2 in sold: A["n_with_" + k2] += 1 / reps
    hours = (ctx["cal"]["t_end"] - ctx["cal"]["t_start"]) / 3.6e6
    out = {"run": ctx["run"], "variant": variant, "reps": reps, "hours": hours, "agg": {}}
    for k, A in agg.items():
        n = max(A["fills"], 1e-9)
        out["agg"][k] = {"fills_per_rep": round(A["fills"], 2), "cash_per_rep": round(A["cash"], 4), "cash_cut_per_rep": round(A["cash_cut"], 4),
                         "cash_day": round(A["cash"] * 24 / hours, 3), "mSOL_per_fill": round(1e3 * A["cash"] / n, 2), "mSOL_per_fill_cut": round(1e3 * A["cash_cut"] / n, 2),
                         "win_share": round(A["wins"] / n, 3),
                         "sold_into_hold_SOL_per_fill": {kk[5:]: round(v / n, 3) for kk, v in A.items() if kk.startswith("sold_")},
                         "share_with_seller": {kk[7:]: round(v / n, 3) for kk, v in A.items() if kk.startswith("n_with_")}}
    json.dump(out, open(outp, "w"), indent=1)
    for k in ["<=5", "6-10", "11-20", "21-40", ">40", "<=10 all", ">10 all", "all"]:
        if k in out["agg"]: print(ctx["run"], k, out["agg"][k])


if __name__ == "__main__":
    a = sys.argv[1:]
    v = "R0"
    if "--variant" in a: i = a.index("--variant"); v = a[i + 1]; del a[i:i + 2]
    main(a[0], a[1], a[2], v)

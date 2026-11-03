#!/usr/bin/env python3
"""MIN-AGE calibration [model vs LIVE on the same live re-arm windows, by the dump's token age]: per live re-arm window of a run, the
replay's model tries (ma5_calib.one_window: live arm time, live stop or the port's own end for filled windows; 8 reps) vs the live
outcome; summed per age bucket (<= 5, 6-10, 11-20, 21-40, > 40 slots; age = dump slot - create slot on the tape).
usage: ma12_agecal.py CTX.pkl OUT.json [REPS]"""
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
import ma4_sim as S, ma5_calib as C5, ma_lib as M
from ma3_ctx import prep_live
from ma11_young import bucket


def main(ctxp, outp, reps=8):
    Wd = S.World(ctxp); tape = Wd.tape; cal = Wd.cal
    agg = collections.defaultdict(lambda: collections.defaultdict(float)); per = []
    for W in Wd.X["wins"]:
        if W["kind"] != "rearm": continue
        a = W["rearm"]["arm_t"] / 1e6
        if not (Wd.t_start <= a <= Wd.t_end) or W["en_slot"] > cal["s_end"]: continue
        P = prep_live(tape, W)
        if P is None: continue
        P.live_exit_slots = 2; P.live_exit_ms = 200
        Wd.anchor(P)
        c = tape.creates.get(W["mint"]) or {}
        if c.get("slot") is None: continue
        age = int(W["trig"]["slot"] - c["slot"])
        t0 = a + cal["first_re"]
        if W["dis"] and W["dis"]["why"] != "filled" and W["dis"].get("t"): t_stop = W["dis"]["t"] / 1e6
        else:
            tl = tape.tok(W["mint"]); re = W["rearm"]
            k_from = Wd.first_seen_ge(tl, a) if re.get("deferred") else None
            t_stop, why, _ = M.natural_end(tape, tl, M.Rule("R0"), Wd.A, a, re.get("arm_slot") or re["check_slot"], W["en_slot"], k_from)
            t_stop += cal["end_dt"].get(why, 0.0)
        rs = [C5.one_window(Wd, P, "rearm", 0.65, t0, t_stop, W["en_slot"], rep) for rep in range(reps)]
        lc, real, fails, nf = C5.live_cash(W)
        b = bucket(age)
        for k in (b, "<=10 all" if age <= 10 else ">10 all", "all"):
            A = agg[k]
            A["windows"] += 1; A["live_fills"] += nf; A["live_cash"] += lc
            A["model_fills"] += np.mean([r["filled"] for r in rs]); A["model_cash"] += np.mean([r["cash_slip"] for r in rs]); A["model_cut"] += np.mean([r["cash_cut"] for r in rs])
            A["model_raw"] += np.mean([r["cash_raw"] for r in rs])
        per.append({"mint": W["mint"], "age": age, "live_fill": nf, "live_cash": lc, "model_fill": float(np.mean([r["filled"] for r in rs])),
                    "model_cash": float(np.mean([r["cash_slip"] for r in rs])), "model_cut": float(np.mean([r["cash_cut"] for r in rs]))})
    out = {"run": Wd.run, "agg": {k: {kk: round(float(vv), 4) for kk, vv in v.items()} for k, v in agg.items()}, "per": per}
    json.dump(out, open(outp, "w"), indent=1)
    order = ["<=5", "6-10", "11-20", "21-40", ">40", "<=10 all", ">10 all", "all"]
    for k in order:
        if k in out["agg"]: print(Wd.run, k, out["agg"][k])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8)

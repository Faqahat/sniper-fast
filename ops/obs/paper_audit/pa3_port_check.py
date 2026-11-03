#!/usr/bin/env python3
"""PAPER AUDIT step 3 [MEASURED]: does the Python port (pa_lib) reproduce the engine's shadow records on the recorder tape?
For every shadow window of the run: the armed rows (presend_disarm) re-run with OUR trades KEPT (the engine sees them): fill yes/no,
crossing x, last trade ahead m, landing a_land, entry slot s_in, exit pnl (follower-drop model) and pnl_naive at 0.55 SOL.
usage: pa3_port_check.py X.pkl OUT.json"""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/obs/paper_audit")
import pa_lib as L


def main(xp, outp):
    X = pickle.load(open(xp, "rb"))
    tp = L.Tape()
    cfg = X["cfg"][-1]["presend"]
    size, tps, sls, drop = cfg["size_sol"], cfg["tp"], cfg["sl"], cfg["drop"]
    ses = max(k[0] for k in X["sh_arm"])
    c = collections.Counter(); ex = []
    per = {}
    cache = {}
    for k, a in sorted(X["sh_arm"].items(), key=lambda kv: kv[1]["t"]):
        if k[0] != ses: continue
        d = X["sh_dis"].get(k)
        if d is None: c["no_disarm"] += 1; continue
        if not (tp.s_lo + 5 <= a["slot"] <= tp.s_hi - 60): c["outside_tape"] += 1; continue
        mint = a["mint"]
        if mint not in cache:
            t = tp.trades(mint)
            cache[mint] = None if t is None else L.build_recs(t, tp.ours, drop_ours=False)
        recs = cache[mint]
        if recs is None: c["mint_not_in_tape"] += 1; continue
        jt = L.find_trig(recs, a["slot"], a["idx"], a.get("j", 0))
        if jt is None: c["trigger_not_in_tape"] += 1; continue
        whale = recs[jt].u
        for r, D in L.ROWS.items():
            if d["rows"][r]["armed"] is not True: continue
            c["rows"] += 1
            f = L.window_fill(recs, jt, whale, D, drop=drop)
            fe = X["sh_fill"].get((k[0], k[1], r)); ee = X["sh_exit"].get((k[0], k[1], r))
            if f["fill"] != (fe is not None):
                c["fill_mismatch"] += 1
                if len(ex) < 15: ex.append({"w": k[1], "row": r, "mint": mint, "port": {kk: f.get(kk) for kk in ("fill", "hit")}, "engine_fill": fe is not None, "engine_hit": d["rows"][r]["hit"]})
                continue
            if not f["fill"]: c["nofill_agree"] += 1; continue
            x, m = recs[f["x"]], recs[f["m"]]
            same_xm = (x.s, x.i, x.j) == (fe["x"]["slot"], fe["x"]["idx"], fe["x"]["j"]) and (m.s, m.i, m.j) == (fe["m"]["slot"], fe["m"]["idx"], fe["m"]["j"])
            if not same_xm:
                c["xm_mismatch"] += 1
                if len(ex) < 30: ex.append({"w": k[1], "row": r, "mint": mint, "port_x": (x.s, x.i, x.j), "eng_x": (fe["x"]["slot"], fe["x"]["idx"]), "port_m": (m.s, m.i), "eng_m": (fe["m"]["slot"], fe["m"]["idx"])})
                continue
            P, e = L.run_path(recs, f["m"], f["a_land"], size, True, tps, sls)
            Pn, en = L.run_path(recs, f["m"], f["a_land"], size, False, tps, sls)
            c["fill_agree"] += 1
            if ee is None: c["no_exit_record"] += 1; continue
            d1 = e["val"] - ee["pnl"]; d2 = en["val"] - ee["pnl_naive"]
            ok1 = abs(d1) < 1e-6; ok2 = abs(d2) < 1e-6
            c["pnl_ok" if ok1 else "pnl_diff"] += 1; c["naive_ok" if ok2 else "naive_diff"] += 1
            if (not ok1 or not ok2) and len(ex) < 45: ex.append({"w": k[1], "row": r, "mint": mint, "port": (e["val"], en["val"], e["so"], P.s_in), "eng": (ee["pnl"], ee["pnl_naive"], ee["exit_slot"], ee["s_in"])})
            per[(k[1], r)] = {"port_pnl": e["val"], "eng_pnl": ee["pnl"], "port_naive": en["val"], "eng_naive": ee["pnl_naive"]}
    out = {"counts": dict(c), "examples": ex}
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps(out["counts"]))
    for e in ex[:20]: print(e)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

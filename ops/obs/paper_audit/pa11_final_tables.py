#!/usr/bin/env python3
"""PAPER AUDIT step 11: the try-level model's final tables, raw and with the follower-drop adjustment (pa9), for B (calibration on the
live-armed windows), C (skipped T2 filters) and D (re-arm), plus the per-hour view for the re-arm.
usage: pa11_final_tables.py PT.pkl SLIP.pkl OUT.json"""
import sys, json, pickle, collections
import numpy as np

FAIL = 5120 / 1e9
REFUND = 1508820 / 1e9


def tot(per, adj, keys, size, var, mode):
    reps = max(len(v) for v in per.values())
    T = []
    for rep in range(reps):
        f = c = fl = 0.0
        for w in keys:
            v = per.get((w, size, var))
            if not v or rep >= len(v): continue
            x = v[rep]; a = (adj.get((w, size, var)) or [None] * reps)[rep]
            f += x["filled"]; fl += x["fails"]
            cc = x["cash"]
            if mode == "slip" and x["filled"] and a is not None: cc += a["delta"]
            if mode == "sol_slip" and x["filled"] and a is not None: cc += a["slip"] - x["gross"]
            c += cc
        T.append((f, c, fl))
    a = np.array(T)
    return {"fills": round(float(a[:, 0].mean()), 1), "cash": round(float(a[:, 1].mean()), 3), "cash_rep_min": round(float(a[:, 1].min()), 3),
            "cash_rep_max": round(float(a[:, 1].max()), 3), "fail_fees": round(float(a[:, 2].mean()) * FAIL, 3)}


def main(pp, sp, outp):
    R = pickle.load(open(pp, "rb")); adj = pickle.load(open(sp, "rb"))["adj"]
    per, meta = R["per"], R["meta"]
    out = {}
    live_w = [w for w, m in meta.items() if not m["syn"]]
    lf = sum(meta[w]["live_fill"] for w in live_w); lr = sum(meta[w]["live_real"] for w in live_w); lfl = sum(meta[w]["live_fails"] for w in live_w)
    out["live"] = {"windows": len(live_w), "fills": lf, "realized": round(lr, 3), "cash": round(lr + lf * REFUND - lfl * FAIL, 3)}
    for mode in ("raw", "slip", "sol_slip"):
        out[f"B_{mode}"] = {var: tot(per, adj, live_w, 0.696, var, mode) for var in ("own", "trig")}
    by = collections.defaultdict(list)
    for w, m in meta.items():
        if m["syn"] and m["syn"] != "rearm": by[m["syn"]].append(w)
    out["C"] = {why: {"windows": len(ws), **{mode: tot(per, adj, ws, 0.696, "syn", mode) for mode in ("raw", "slip", "sol_slip")}} for why, ws in by.items()}
    re_w = [w for w, m in meta.items() if m["syn"] == "rearm" and (w, 0.65, "syn") in per]
    ts = sorted(meta[w]["t"] for w in re_w)
    hours = (ts[-1] - ts[0]) / 3.6e6
    D = {"windows": len(re_w), "hours": round(hours, 2)}
    for sz in (0.40, 0.65, 0.696):
        D[f"{sz:.2f}"] = {mode: tot(per, adj, re_w, sz, "syn", mode) for mode in ("raw", "slip", "sol_slip")}
    for key in ("r5_skip", "end_why"):
        g = collections.defaultdict(list)
        for w in re_w:
            re = meta[w]["rearm"] or {}
            k = re.get("r5_skip") if key == "r5_skip" else (re.get("end") or {}).get("why")
            g[str(k)].append(w)
        D[f"by_{key}_0.65"] = {k: {"windows": len(ws), "raw": tot(per, adj, ws, 0.65, "syn", "raw"), "slip": tot(per, adj, ws, 0.65, "syn", "slip")} for k, ws in g.items()}
    # by PKT hour (0.65, slip)
    hb = collections.defaultdict(list)
    for w in re_w: hb[int(((meta[w]["t"] / 1e3 + 5 * 3600) // 3600) % 24)].append(w)
    D["by_pkt_hour_0.65_slip"] = {h: dict(windows=len(ws), **tot(per, adj, ws, 0.65, "syn", "slip")) for h, ws in sorted(hb.items())}
    out["D"] = D
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

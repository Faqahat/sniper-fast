#!/usr/bin/env python3
"""PAPER AUDIT step 8: tables from the try-level model (pa7): B calibration vs live, C skipped-filter re-score, D re-arm re-score.
Cash = SOL back after pump's fee - size - fixed costs (2.015 mSOL: tip, fees, sell tip, ATA rent net of its refund; MEASURED on r37)
       - 5,120 lamports per landed try that did not fill.  Realized basis (live's REALIZED lines) = cash + fails x 5,120 - 1.509 mSOL refund.
usage: pa8_pt_tables.py PT.pkl X.pkl OUT.json"""
import sys, json, pickle, collections, statistics
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as C37

FAIL = C37.FAIL / 1e9
REFUND = C37.REFUND / 1e9


def totals(per, keys, size, var, reps):
    """per-rep totals over windows: fills, cash, positions-only cash (no failed tries), failed tries"""
    T = []
    for rep in range(reps):
        f = c = pos = fl = 0.0
        for w in keys:
            v = per.get((w, size, var))
            if not v or rep >= len(v): continue
            x = v[rep]
            f += x["filled"]; c += x["cash"]; fl += x["fails"]
            if x["filled"]: pos += x["cash"] + x["fails"] * FAIL
        T.append((f, c, pos, fl))
    a = np.array(T)
    return {"fills": float(a[:, 0].mean()), "cash": float(a[:, 1].mean()), "cash_min": float(a[:, 1].min()), "cash_max": float(a[:, 1].max()),
            "positions": float(a[:, 2].mean()), "fail_tries": float(a[:, 3].mean()), "fail_fees": float(a[:, 3].mean()) * FAIL}


def main(pp, xp, outp):
    R = pickle.load(open(pp, "rb")); X = pickle.load(open(xp, "rb"))
    per, meta = R["per"], R["meta"]
    reps = max(len(v) for v in per.values())
    out = {"R": R["R"], "anchor": R["anchor"], "reps": reps}
    # A
    A = R["A"]
    out["A_real_tries"] = {"live_fills": sum(a["live_fill"] for a in A), "sim_fills": sum(a["sim_fill"] for a in A), "same_try": sum(a["same"] for a in A),
                           "live_realized": sum(a["live_real"] for a in A), "sim_realized": sum(a["sim_real"] for a in A),
                           "live_fail_tries": sum(a["live_fails"] for a in A), "sim_fail_tries": sum(a["sim_fails"] for a in A)}
    live_w = [w for w, m in meta.items() if not m["syn"]]
    live_real = sum(meta[w]["live_real"] for w in live_w)
    live_fills = sum(meta[w]["live_fill"] for w in live_w)
    live_fail = sum(meta[w]["live_fails"] for w in live_w)
    live_cash = live_real + live_fills * REFUND - live_fail * FAIL
    out["live"] = {"windows": len(live_w), "fills": live_fills, "realized": live_real, "cash": live_cash, "fail_tries": live_fail}
    # B
    for var in ("own", "trig"):
        t = totals(per, live_w, 0.696, var, reps)
        t["realized_eq"] = t["positions"] - t["fills"] * REFUND
        t["cash_minus_live"] = t["cash"] - live_cash
        out[f"B_{var}"] = t
    # per-window agreement (trig variant): live fill vs model fill probability
    agg = collections.Counter(); pnl = collections.defaultdict(float)
    for w in live_w:
        v = per.get((w, 0.696, "trig"))
        if not v: continue
        pf = statistics.mean(x["filled"] for x in v)
        lf = meta[w]["live_fill"]
        agg["live_fill"] += lf; agg["model_fill_on_live_filled"] += pf if lf else 0; agg["model_fill_on_live_unfilled"] += pf if not lf else 0
        pnl["model_pos_on_live_filled"] += statistics.mean(x["cash"] + x["fails"] * FAIL for x in v if True) if lf else 0
        pnl["model_pos_on_live_unfilled"] += statistics.mean((x["cash"] + x["fails"] * FAIL) for x in v) if not lf else 0
    out["B_trig_split"] = {"counts": dict(agg), "pnl": dict(pnl), "live_cash_on_filled": sum(meta[w]["live_real"] + REFUND for w in live_w if meta[w]["live_fill"])}
    # C: skipped T2 triggers
    C = {}
    by = collections.defaultdict(list)
    for w, m in meta.items():
        if m["syn"] and m["syn"] != "rearm": by[m["syn"]].append(w)
    for why, ws in sorted(by.items(), key=lambda kv: -len(kv[1])):
        t = totals(per, ws, 0.696, "syn", reps)
        t["windows"] = len(ws); t["saved_cash"] = -t["cash"]; t["realized_eq_positions"] = t["positions"] - t["fills"] * REFUND
        C[why] = t
    out["C_skips"] = C
    # D: re-arm
    D = {}
    re_w = [w for w, m in meta.items() if m["syn"] == "rearm"]
    ts = sorted(meta[w]["t"] for w in re_w)
    hours = (ts[-1] - ts[0]) / 3.6e6 if len(ts) > 1 else None
    for sz in (0.40, 0.65, 0.696):
        t = totals(per, re_w, sz, "syn", reps); t["windows"] = len(re_w); t["hours"] = hours
        t["cash_per_hour"] = t["cash"] / hours if hours else None; t["cash_per_day"] = t["cash"] / hours * 24 if hours else None
        D[f"{sz:.3f}"] = t
    # split by r5_skip and by end reason at 0.65
    for key in ("r5_skip", "end_why", "superseded"):
        g = collections.defaultdict(list)
        for w in re_w:
            re = meta[w]["rearm"] or {}
            k = re.get("r5_skip") if key == "r5_skip" else ((re.get("end") or {}).get("why") if key == "end_why" else bool(re.get("superseded")))
            g[str(k)].append(w)
        D[f"by_{key}_0.65"] = {k: dict(totals(per, ws, 0.65, "syn", reps), windows=len(ws)) for k, ws in g.items()}
    out["D_rearm"] = D
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:12000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

#!/usr/bin/env python3
"""PAPER AUDIT step 15: the shadow's own row model on the SKIPPED T2 triggers, re-priced the right way (for the filter-savings table):
row c (and a) on the recorder tape without our trades, at 0.696 SOL by curve math, 2-slot exit and the live-like exit (sell lands
H = 296.5 ms after the fill on the real block clock), with the follower-drop model; cash = gross - 2.015 mSOL per fill (MEASURED live
fixed cost net of the ATA refund). Failed-try fees are added from the try-level model (pa11) in the report.
usage: pa15_skips_port.py X.pkl OUT.json [H_ms]"""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/obs/paper_audit")
import pa_lib as L

FIX_CASH = (3523961 - 1508820) / 1e9


def main(xp, outp, H=296.5):
    X = pickle.load(open(xp, "rb")); tp = L.Tape()
    cfg = X["cfg"][-1]["presend"]
    agg = collections.defaultdict(lambda: collections.defaultdict(float))
    cache = {}
    for s in X["lv_skip"]:
        if s.get("kind") == "rearm" or not s.get("trig"): continue
        tg = s["trig"]; why = s["why"]
        mint = tg["mint"]
        if mint not in cache:
            t = tp.trades(mint)
            cache[mint] = None if t is None else L.build_recs(t, tp.ours, drop_ours=True)
        recs = cache[mint]
        A = agg[why]; A["windows"] += 1
        if recs is None: A["no_tape"] += 1; continue
        jt = L.find_trig(recs, tg["slot"], tg["idx"], tg.get("j", 0))
        if jt is None: A["no_trig"] += 1; continue
        for r, D in (("a", 0.0), ("c", 10.0)):
            f = L.window_fill(recs, jt, recs[jt].u, D, drop=cfg["drop"])
            if not f["fill"]: continue
            A[f"{r}_fills"] += 1
            for sz in (0.55, 0.696):
                P, e = L.run_path(recs, f["m"], f["a_land"], sz, True, cfg["tp"], cfg["sl"])
                if e: A[f"{r}_e2_slip_{sz}"] += e["val"]
            m = recs[f["m"]]
            v = L.value_at(recs, f["m"], 0.696, True, L.cc_of(tp.maxi, m.s, m.i) + H, tp.maxi, by_cc=True)
            if v: A[f"{r}_ecc_slip_0.696"] += v["gross"]
    out = {}
    for why, A in agg.items():
        d = {k: round(v, 4) for k, v in A.items()}
        for r in ("a", "c"):
            n = A[f"{r}_fills"]
            d[f"{r}_cash_e2_0.696"] = round(A[f"{r}_e2_slip_0.696"] - n * FIX_CASH, 3)
            d[f"{r}_cash_live_exit_0.696"] = round(A[f"{r}_ecc_slip_0.696"] - n * FIX_CASH, 3)
        out[why] = d
    json.dump(out, open(outp, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 296.5)

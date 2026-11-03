#!/usr/bin/env python3
"""CUSTOM37 step 3: CALIBRATION. Replay every live window at its run's OWN live config with its real tries and compare with live:
fill vs no fill (same try), curve P&L per fill (model vs the real sell), realized per fill, failed-try fees.
Also the PHANTOM check (INFERRED part): every real try replaced by phantom tries (same window clock, same stop rules), expected fills
and P&L vs live, so the phantom model's bias is known before it is used for k / window / deeper-limit continuation.
Out: stdout + /home/moiz/sniper-data/custom37/calib_<run>.json"""
import sys, json, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L


def live_cfg(X):
    c = X["cfg"][-1]["presend_live"]; q = (c.get("quiet") or {}).get("stop")
    return dict(L.BASE, drop=c["drop"], size=c["spend"] / 1e9, k=c["k"], win=c["window_slots"], dl=c["deadline_slots"], exit_ms=c.get("exit_ms") or 10 ** 9,
                exit_slots=c["exit_slots"], tp=c["tp"], sl=c["sl"], qstop=tuple(int(v) for v in q.split(":")) if q else None)


def main(run, nph_reps=6):
    X, wins, R = L.load(run)
    cfg = live_cfg(X)
    print(f"== {run}: windows {len(wins)} cfg {cfg}")
    print(f"   run ctx: L med {np.median(R.L):.1f} ms (q10 {np.percentile(R.L, 10):.1f} q90 {np.percentile(R.L, 90):.1f}), unseen {R.p_unseen:.3f}, D med {np.median(R.D):.1f}, "
          f"C {R.C:.0f}, tau {R.tau:.1f}, bias exp {R.b_exp:.1f} ws {R.b_ws:.1f} q {R.b_q:.1f}")
    out = L.run_sim(wins, R, cfg, rep=0)
    agree = collections.Counter(); errs = []; rows = []
    for P in wins:
        r = out[id(P)]
        lf = P.fill is not None
        same = r["filled"] and lf and r.get("live_try")
        agree[(lf, r["filled"], bool(same) if r["filled"] and lf else None)] += 1
        live_fails = sum(1 for tr in P.tries if tr["land"] is not None and tr["res"] != "ok")
        row = {"w": P.W["w"], "ses": P.W["ses"], "mint": P.mint, "live_fill": lf, "sim_fill": r["filled"], "same_try": bool(same), "live_fails": live_fails, "sim_fails": r["fails"],
               "nph": r["nph"]}
        if lf and P.close and P.close.get("sol_out_curve") is not None:
            live_curve = P.close["sol_out_curve"] * (1 - L.FR) - P.close["sol_in_curve"] * (1 + L.FR) if False else P.close["sol_out_curve"] * (1 - L.FR) - P.spend_live
            row["live_curve"] = live_curve; row["live_real"] = P.live_pnl
            if r["filled"]:
                row["sim_curve"] = r["gross"]
                if same: errs.append(r["gross"] - live_curve)
        rows.append(row)
    n = len(wins); nlf = sum(1 for P in wins if P.fill); nsf = sum(1 for P in wins if out[id(P)]["filled"])
    print(f"   windows: live fills {nlf}, sim fills {nsf}; (live, sim, same try): {dict(agree)}")
    e = np.array(errs) / 1e6
    if len(e): print(f"   curve P&L per fill (same try) model - live: mean {e.mean():+.4f} mSOL, mean abs {abs(e).mean():.4f}, max abs {abs(e).max():.4f} (n {len(e)})")
    lf = sum(r["live_fails"] for r in rows); sf = sum(r["sim_fails"] for r in rows)
    print(f"   failed landed tries: live {lf} sim {sf}")
    tot_live = sum((P.live_pnl or 0) for P in wins) / 1e9
    tot_sim_real = sum((out[id(P)]["pnl"] + out[id(P)]["fails"] * L.FAIL - (L.FIX_REAL - L.FIX)) for P in wins if out[id(P)]["filled"]) / 1e9
    print(f"   realized-equivalent P&L: live {tot_live:+.4f} SOL, sim {tot_sim_real:+.4f} SOL")
    # phantom check: the same windows with phantom tries only
    ph = []
    for rep in range(nph_reps):
        cfg2 = dict(cfg)
        res = phantom_only(wins, R, cfg2, rep)
        ph.append(res)
    pf = np.mean([sum(1 for v in r.values() if v["filled"]) for r in ph])
    pp = np.mean([sum(v["pnl"] + v["fails"] * L.FAIL - (L.FIX_REAL - L.FIX) for v in r.values() if v["filled"]) for r in ph]) / 1e9
    pfail = np.mean([sum(v["fails"] for v in r.values()) for r in ph])
    print(f"   PHANTOM-only (INFERRED model, {nph_reps} reps): fills {pf:.1f} (live {nlf}), realized-eq P&L {pp:+.4f} (live {tot_live:+.4f}), failed tries {pfail:.0f} (live {lf})")
    json.dump({"run": run, "cfg": {k: v for k, v in cfg.items()}, "rows": rows, "agree": {str(k): v for k, v in agree.items()}, "phantom": {"fills": pf, "pnl": pp, "fails": pfail}},
              open(f"{L.D}/calib_{run}.json", "w"))


def phantom_only(wins, R, cfg, rep):
    """every real try dropped: the window is armed from its first try time to its stop, phantoms only (no one-position knock-on)"""
    out = {}
    for P in wins:
        rng = np.random.default_rng([99, rep, P.W["ses"], P.W["w"]])
        saved = P.tries; t0 = P.tries[0]["t"] if P.tries else P.t_trig + R.first; dis = P.dis
        P.tries = []
        # stop: the live stop (minus a fill: phantoms run to the no-fill stop)
        t_stop, en = L.stop_times(P, cfg, R)
        P.dis = None
        try:
            r = L.window_sim(P, cfg, R, rng, (), ((t0, t_stop),))
        finally:
            P.tries = saved; P.dis = dis
        out[id(P)] = r
    return out


if __name__ == "__main__":
    for run in sys.argv[1:]: main(run)

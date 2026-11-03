#!/usr/bin/env python3
"""PAPER AUDIT step 7: the TRY-LEVEL model (custom37's c37lib replay, unchanged) on the full r37 run.
 A. live windows, real tries -> must reproduce live (MEASURED check);
 B. live windows, PHANTOM tries only (the INFERRED model: sends every 212/k ms at the run's measured unique-try rate, landing after a
    latency drawn from the run's real landed tries, signed on the latest state seen, live stop rules, live exit with measured sell
    latencies) -> its bias vs live = the calibration of the model used for C and D;
 C. SKIPPED T2 triggers (create_slot / young_age / quiet / ...), phantom tries only -> what live would have made had it armed them;
 D. RE-ARM windows (observatory), phantom tries only, armed at the record's arm time, stopped at its end.
Clock anchor of a window without real tries: its own trigger (feed arrival - block-clock position) + the median live (try anchor -
trigger anchor) offset; custom37's nearest-window anchor is kept as a check.
usage: pa7_ptmodel.py C37DIR OUT.pkl [REPS]"""
import sys, pickle, collections, statistics
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/custom37")
import c37lib as L

REPS = 8


def cfg_live(X):
    c = X["cfg"][-1]["presend_live"]; q = (c.get("quiet") or {}).get("stop")
    return dict(L.BASE, drop=c["drop"], size=c["spend"] / 1e9, k=c["k"], win=c["window_slots"], dl=c["deadline_slots"], exit_ms=c.get("exit_ms") or 10 ** 9,
                exit_slots=c["exit_slots"], tp=c["tp"], sl=c["sl"], qstop=tuple(int(v) for v in q.split(":")) if q else None)


_orig_stop = L.stop_times


def stop_times(P, cfg, R):
    if getattr(P, "re_stop", None) is not None: return P.re_stop, P.re_en
    return _orig_stop(P, cfg, R)


L.stop_times = stop_times


def phantom_only(P, R, cfg, rep, salt=99):
    rng = np.random.default_rng([salt, rep, P.W["ses"], P.W["w"]])
    saved = P.tries; dis = P.dis
    P.tries = []
    t_stop, en = L.stop_times(P, cfg, R)
    t0 = P.t_trig + R.first
    P.dis = None
    try:
        r = L.window_sim(P, cfg, R, rng, (), ((t0, t_stop),))
    finally:
        P.tries = saved; P.dis = dis
    return r


def main(d, outp, reps=REPS):
    L.D = d
    X, wins, R = L.load("r37f")
    cfg = cfg_live(X)
    live = [P for P in wins if not P.W.get("synthetic")]
    syn = [P for P in wins if P.W.get("synthetic")]
    print(f"windows: live {len(live)} synthetic {len(syn)} | R: L med {np.median(R.L):.1f} ms (p10 {np.percentile(R.L, 10):.1f} p90 {np.percentile(R.L, 90):.1f}) unseen {R.p_unseen:.3f} "
          f"D med {np.median(R.D):.1f} tau {R.tau:.1f} first {R.first:.1f} k_eff {R.k_eff:.2f} b_exp {R.b_exp:.1f} b_ws {R.b_ws:.1f} b_q {R.b_q:.1f}")
    # clock anchors: trigger-based for windows without real tries
    cc = live[0].cc
    def trig_anchor(P):
        tg = P.W["trig"]; return P.t_trig - cc(tg["slot"], tg["idx"])
    d_off = [P.off - trig_anchor(P) for P in live if not P.off_est]
    d_offs = [P.off_s - trig_anchor(P) for P in live if not P.off_est]
    m_off, m_offs = statistics.median(d_off), statistics.median(d_offs)
    print(f"anchor: try-based off - trigger-based off: median {m_off:.1f} ms, p10 {np.percentile(d_off, 10):.1f} p90 {np.percentile(d_off, 90):.1f}; off_s - trigger: median {m_offs:.1f}")
    nearest_err = []
    for P in syn:
        ta = trig_anchor(P)
        nearest_err.append(P.off - (ta + m_off))
        P.off = ta + m_off; P.off_s = ta + m_offs; P.off_est = "trigger"
    print(f"synthetic windows: nearest-window anchor - trigger anchor: median {np.median(nearest_err):.1f} ms, p10 {np.percentile(nearest_err, 10):.1f} p90 {np.percentile(nearest_err, 90):.1f}")
    # re-arm windows: arm time, end time, last slot
    for P in syn:
        if P.W["synthetic"] != "rearm": continue
        re = P.W["rearm"]
        P.a_trig = L_arr(P.W["trig"]["slot"], P.W["trig"]["idx"])
        P.re_stop = re["end"]["t"] / 1e6 if re.get("end") and re["end"].get("t") else None
        P.re_en = P.W["en_slot"]
        P.t_trig = re["arm"]["t"] / 1e6 - R.first     # phantom sends start at the arm time
    res = {"cfg": cfg, "R": {"L_med": float(np.median(R.L)), "unseen": R.p_unseen, "D_med": float(np.median(R.D)), "tau": R.tau, "first": R.first, "k_eff": R.k_eff},
           "anchor": {"m_off": m_off, "m_offs": m_offs, "nearest_minus_trigger_med": float(np.median(nearest_err))}}
    # A. real tries
    out = L.run_sim(live, R, cfg, rep=0)
    A = []
    for P in live:
        r = out[id(P)]
        A.append({"w": P.W["w"], "live_fill": P.fill is not None, "sim_fill": r["filled"], "same": bool(r.get("live_try")), "live_real": (P.live_pnl or 0) / 1e9 if P.fill else 0.0,
                  "sim_real": ((r["pnl"] + r["fails"] * L.FAIL - (L.FIX_REAL - L.FIX)) / 1e9) if r["filled"] else 0.0, "sim_fails": r["fails"],
                  "live_fails": sum(1 for tr in P.tries if tr["land"] is not None and tr["res"] != "ok")})
    res["A"] = A
    print(f"A real tries: live fills {sum(a['live_fill'] for a in A)} sim fills {sum(a['sim_fill'] for a in A)} same try {sum(a['same'] for a in A)} | realized live {sum(a['live_real'] for a in A):+.4f} "
          f"sim {sum(a['sim_real'] for a in A):+.4f} | failed tries live {sum(a['live_fails'] for a in A)} sim {sum(a['sim_fails'] for a in A)}")
    # B / C / D: phantom-only, reps. Live windows twice: "own" = their own try-based clock anchor (custom37's check), "trig" = the
    # trigger-based anchor the windows without real tries get (the calibration that applies to C and D)
    per = collections.defaultdict(list)
    own = {id(P): (P.off, P.off_s) for P in live}
    trg = {id(P): (trig_anchor(P) + m_off, trig_anchor(P) + m_offs) for P in live}
    def one_pass(var, rep):
        for P in (live if var != "syn" else syn):
            if P.W.get("synthetic") == "rearm" and P.re_stop is None: continue
            if var in ("own", "trig"): P.off, P.off_s = (own if var == "own" else trg)[id(P)]
            sizes = (0.696,) if P.W.get("synthetic") != "rearm" else (0.40, 0.65, 0.696)
            for sz in sizes:
                c2 = dict(cfg, size=sz, qstop=(None if P.W.get("synthetic") == "rearm" else cfg["qstop"]))
                r = phantom_only(P, R, c2, rep)
                per[(P.W["w"], sz, var)].append({"filled": r["filled"], "cash": r["pnl"] / 1e9, "gross": (r.get("gross") or 0) / 1e9 if r["filled"] else 0.0, "fails": r["fails"],
                                                 "n_tries": r.get("n_tries", 0), "why": r.get("why"), "src": r.get("src"), "fs": r.get("fs"), "fi": r.get("fi"),
                                                 "c_sell": r.get("c_sell"), "tok": r.get("tok")})
    for rep in range(reps):
        for var in ("own", "trig", "syn"): one_pass(var, rep)
        print("rep", rep, "done", flush=True)
    for P in live: P.off, P.off_s = own[id(P)]
    res["per"] = dict(per)
    res["meta"] = {P.W["w"]: {"syn": P.W.get("synthetic"), "mint": P.mint, "t": P.t_trig, "age": P.W["trig"].get("age_slots"), "live_fill": P.fill is not None,
                              "live_real": (P.live_pnl or 0) / 1e9 if P.fill else 0.0,
                              "live_fails": sum(1 for tr in P.tries if tr["land"] is not None and tr["res"] != "ok"),
                              "rearm": ({k: v for k, v in P.W["rearm"].items() if k != "rows_full"} if P.W.get("synthetic") == "rearm" else None)} for P in wins}
    pickle.dump(res, open(outp, "wb"))


def L_arr(s, i):
    size = max(400, i + 1)
    return s * L.SMS + (i / size) * L.SMS


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else REPS)

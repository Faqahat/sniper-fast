#!/usr/bin/env python3
"""QUIET4 step 5: per-window values of every r37 trigger under each QUIET stop N:M, at 0% and -20% followers.
  ARMED windows: the paired try-level replay (custom37 c37lib) with their REAL tries, all armed windows together in trigger order
     (one-position knock-on). At the live config (stop 5:2, 0% cut) it reproduces live exactly; other stops change only what the stop
     changes (a tighter stop drops real tries / fills; a looser one adds phantom tries after the live stop: INFERRED).
  VIRTUAL windows (QUIET-skipped, age-1-skipped, blocked_armed): phantom tries only (INFERRED), paused while any LIVE position was open
     (one-position), modelled stops; "M1" mode. Calibrated in the same mode on the armed windows' virtual twins (other windows' live
     positions as pauses) -> calib_m1 rows below.
Value = realized-equivalent P&L - 5120 lamports per landed failed try (SOL). REPS worlds each, means.
Out: /home/it/sniper-data/presend_quiet4/values_r37.pkl {"stops": [...], "cuts": [...], "armed": {key: {(stop, cut): (v, f)}}, "virt": {...}, "calib_m1": {...}}"""
import sys, pickle, collections, time, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filter/quiet4")
import q3lib as Q
L = Q.L
REPS = 8
STOPS = [(3, 2), (4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (4, 3), (5, 3), (6, 3), (7, 3), (8, 3), None]
CUTS = [0.0, 0.2]
_C = {}


def init():
    X, wins, R = Q.load()
    A = [P for P in wins if P.W["kind"] == "armed"]
    Vw = [P for P in wins if P.W["kind"] != "armed"]
    lp = L.live_positions(A)
    VT = {id(P): Q.virtualize(P, R) for P in A}
    _C.update(X=X, wins=wins, R=R, A=A, V=Vw, lp=lp, VT=VT)


def key(P): return f"{P.W['ses']}:{P.W['w']}"


def pauses_for(P, lp, own=None):
    t0 = P.t_trig; t1 = P.t_trig + 4000.0
    return [(a, b) for a, b, pid in lp if b > t0 and a < t1 and pid != own]


def job(args):
    stop, cut = args
    A, Vw, R, lp, VT = _C["A"], _C["V"], _C["R"], _C["lp"], _C["VT"]
    cfg = dict(L.BASE, qstop=stop, cut=cut)
    arm = collections.defaultdict(lambda: np.zeros(2)); virt = collections.defaultdict(lambda: np.zeros(2)); cal = collections.defaultdict(lambda: np.zeros(2))
    deterministic = (stop == (5, 2) and cut == 0.0)
    nrep = 1 if deterministic else REPS
    for rep in range(nrep):
        o = L.run_sim(A, R, cfg, rep=rep, livepos=lp)
        for P in A:
            f, v, _ = Q.value(o[id(P)]); arm[key(P)] += [v / nrep, f / nrep]
    for rep in range(REPS):
        for P in Vw:
            rng = np.random.default_rng([23, rep, P.W["ses"], abs(P.W["w"]), 7])
            r = L.window_sim(P, cfg, R, rng, pauses_for(P, lp), ())
            f, v, _ = Q.value(r); virt[key(P)] += [v / REPS, f / REPS]
        if stop in ((5, 2), (6, 2), (4, 2)):
            for P in A:
                V = VT[id(P)]
                rng = np.random.default_rng([29, rep, P.W["ses"], abs(P.W["w"]), 7])
                r = L.window_sim(V, cfg, R, rng, pauses_for(P, lp, own=id(P)), ())
                f, v, _ = Q.value(r); cal[key(P)] += [v / REPS, f / REPS]
    return stop, cut, {k: tuple(v) for k, v in arm.items()}, {k: tuple(v) for k, v in virt.items()}, {k: tuple(v) for k, v in cal.items()}


def main():
    t0 = time.time()
    init()
    out = {"stops": STOPS, "cuts": CUTS, "armed": collections.defaultdict(dict), "virt": collections.defaultdict(dict), "calib_m1": collections.defaultdict(dict)}
    jobs = [(s, c) for s in STOPS for c in CUTS]
    with Pool(6, initializer=init) as pool:
        for stop, cut, arm, virt, cal in pool.imap_unordered(job, jobs):
            for k, v in arm.items(): out["armed"][k][(stop, cut)] = v
            for k, v in virt.items(): out["virt"][k][(stop, cut)] = v
            for k, v in cal.items(): out["calib_m1"][k][(stop, cut)] = v
            print(stop, cut, "armed sum %+.3f" % sum(v[0] for v in arm.values()), "virt sum %+.3f" % sum(v[0] for v in virt.values()),
                  ("calib twins %+.3f" % sum(v[0] for v in cal.values())) if cal else "", f"{time.time()-t0:.0f}s", flush=True)
    A = _C["A"]
    out["live"] = {key(P): (P.W["v"], 1 if P.fill else 0) for P in A}
    out["meta"] = {key(P): {"kind": P.W["kind"]} for P in _C["wins"]}
    out = {k: (dict(v) if isinstance(v, collections.defaultdict) else v) for k, v in out.items()}
    pickle.dump(out, open(f"{L.D}/values_r37.pkl", "wb"))
    lv = sum(P.W["v"] for P in A); cv = sum(out["calib_m1"][key(P)][((5, 2), 0.0)][0] for P in A)
    print(f"M1 calibration (armed twins, live-position pauses, stop 5:2): live {lv:+.3f} model {cv:+.3f} SOL over {len(A)} windows; "
          f"fills live {sum(1 for P in A if P.fill)} model {sum(out['calib_m1'][key(P)][((5, 2), 0.0)][1] for P in A):.1f}")


if __name__ == "__main__":
    main()

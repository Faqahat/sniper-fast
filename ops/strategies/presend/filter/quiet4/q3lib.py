"""QUIET4 replay helpers on top of custom37/c37lib.py (read-only use of it; its data dir is pointed at presend_quiet4).
VIRTUAL window = a trigger with no real tries (QUIET / age / blocked skip in r37): it is replayed with PHANTOM tries only (INFERRED:
sent every 212/k ms at the run's measured unique-try rate from the run's median first-try delay, landing after a latency drawn from
the run's real landed tries; its stops (expiry, whale sold, QUIET N:M) modelled; its exit uses the run's measured sell latencies).
`virtualize(P)` turns an ARMED window into its virtual twin (live tries, stop, fill, exit, arrival map and clock anchors removed;
the anchors re-taken from its own trigger, as a skipped window gets them) for the calibration."""
import sys, copy, bisect, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/custom37")
import c37lib as L
L.D = "/home/it/sniper-data/presend_quiet4"
FAIL = L.FAIL
REALEQ = L.FIX_REAL - L.FIX      # pnl (cash, incl. the ATA refund) -> realized-equivalent


def trigger_anchor_fit(wins, R):
    """the clock anchors from the TRIGGER itself (its feed arrival t_trig and its block position): off = t_trig - cc(trigger) + d1,
    off_s = t_trig - s0 x 212 + d2, d1 / d2 = medians over the armed windows with their own anchors (MEASURED). The nearest other
    window's anchor (c37lib's fallback) is wrong by a median 0.3 s (q90 1.5 s): windows are ~30 s apart and the slot clock drifts."""
    own = [P for P in wins if not getattr(P, "off_est", True)]
    R.d1 = float(np.median([P.off - (P.t_trig - P.cc(P.s0, P.i0)) for P in own]))
    R.d2 = float(np.median([P.off_s - (P.t_trig - P.s0 * L.SMS) for P in own]))


def trigger_anchor(P, R):
    return P.t_trig - P.cc(P.s0, P.i0) + R.d1, P.t_trig - P.s0 * L.SMS + R.d2


def load(run="r37"):
    if run != "r37": L.D = "/home/it/sniper-data/custom37"      # the earlier runs' pickles (custom37, read-only)
    else: L.D = "/home/it/sniper-data/presend_quiet4"
    X, wins, R = L.load(run)
    trigger_anchor_fit(wins, R)
    # windows without landed tries (virtual ones, armed ones whose tries never landed): anchors from their own trigger
    for P in wins:
        if getattr(P, "off_est", False): P.off, P.off_s = trigger_anchor(P, R)
    return X, wins, R


def nearest_anchor(R, t, exclude_t=None):
    k = bisect.bisect_left(R.anchor_t, t)
    cand = [q for q in (k - 2, k - 1, k, k + 1) if 0 <= q < len(R.anchor_t) and (exclude_t is None or abs(R.anchor_t[q] - exclude_t) > 1e-6)]
    q = min(cand, key=lambda q: abs(R.anchor_t[q] - t))
    return R.anchor[q][1], R.anchor[q][2]


def virtualize(P, R):
    V = copy.copy(P)
    V.tries = []; V.dis = None; V.fill = None; V.fill_rx = None; V.exit = None; V.sell = None; V.close = None; V.live_pnl = None
    V.rx_map = {}
    V.off, V.off_s = trigger_anchor(P, R)
    V.virt_of = P
    L.P_by_id[id(V)] = V
    return V


def value(r):
    """a window result -> (filled, realized-equivalent value in SOL incl. failed-try fees, fails)"""
    if r.get("skip"): return 0, 0.0, 0
    if r["filled"]: return 1, (r["pnl"] - REALEQ) / 1e9, r["fails"]
    return 0, r["pnl"] / 1e9, r["fails"]


def alone(P, R, cfg, rep, seed=11):
    """one window replayed alone (no one-position knock-on)"""
    rng = np.random.default_rng([seed, rep, P.W["ses"], abs(P.W["w"]), 7])
    return L.window_sim(P, cfg, R, rng, (), ())

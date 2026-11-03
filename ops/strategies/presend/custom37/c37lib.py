"""CUSTOM37 replay library: a PAIRED try-level replay of live pre-send windows (engine dip25 rules, pslive.rs / presend_live.rs).

Clocks: block-position clock cc(slot, idx) = slot*212 + (idx+0.5)/(maxi(slot)+1)*212 ms (the engine's SMS = 212); feed clock = unix ms.
Per window the feed clock = block clock + off_w (median over the window's landed tries of first_rx - cc(landing)) [MEASURED anchors].

Curve: outside trades only (our wallets removed), re-simulated by deltas from the trigger's post-trade state once one of our own trades
is passed (buys keep their SOL, sells their tokens: the wave37 walk); before that the recorded states are used (exact).

A try = one unique signed tx (byte-identical resends share a signature: one tx). Real tries keep their real landing (slot, idx);
it fills iff it landed by its deadline and the curve before its landing position gives >= min_out (pump's 6042 check) at the
config's limit (presend_live::limit_min_out on the try's signing state). The first filling try in chain order is our fill.
Phantom tries (INFERRED) fill the periods the live window did not cover (k > live, a longer window / later stop, a deeper limit
after the live fill, live one-position pauses): sent every 212/k ms, signed on the latest state seen, landing L ms later on the
block clock (L drawn from the run's real landed tries; unseen share kept).

Exit (MEASURED latencies): decision at fill seen + exit_ms (or the first TP / SL trade seen), the sell lands D ms (block clock)
after the decision; D = the window's own live value when it filled live, else drawn from the run's live D values.
Baseline (live config, live fill try) uses the REAL sell landing position.
P&L (cash): sell SOL x (1 - fee) - spend - FIX (tip 0.2 + buy fee 0.00512 + sell fee and tip 1.805 + ATA rent 1.51384 - its refund
1.50882 mSOL, all MEASURED on r37) - 5120 per landed try that did not fill."""
import bisect, math, random, pickle, json, numpy as np

SMS = 212.0
FR = 0.012500000186264515          # pump fee (95 + 30 bps, f32 as the engine)
FIX_REAL = 3523961                  # realized - curve P&L per round trip (MEASURED, all 168 r37 fills)
REFUND = 1508820                    # ATA close: rent back - close fee (MEASURED)
FIX = FIX_REAL - REFUND             # cash fixed cost per round trip
FAIL = 5120                         # a landed failed try (5000 + 120k CU x 1000 uL)
UNTRADE_V = 100_000_000_000
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
D = "/home/moiz/sniper-data/custom37"

BASE = dict(drop=0.12, quote=None, size=0.696, k=8, win=10, dl=1, exit_ms=200, exit_slots=2, tp=0.20, sl=0.20, flat=None, qstop=(5, 2),
            cut=0.0, seed=0)


def limit_min_out(vsol, vtok, spend, fr, drop):
    """presend_live::limit_min_out -> (min tokens out, limit price)"""
    v, t = float(vsol), float(vtok)
    k = v * t
    vl = min(v * math.sqrt(1.0 - drop), UNTRADE_V - 1.0)
    tl = k / vl
    x = spend / (1.0 + fr)
    return math.floor(tl * x / (vl + x)), vl / tl


def buy_out(V, T, spend, fr=FR):
    x = int(spend / (1.0 + fr))
    return int(T * x // (V + x)), x


def sell_out(V, T, tok):
    return V * tok / (T + tok)


class Win:
    """one live window, prepared for replay"""
    pass


def prep_run(run):
    X = pickle.load(open(f"{D}/win_{run}.pkl", "rb"))
    TP = pickle.load(open(f"{D}/tape_{run}.pkl", "rb"))
    maxi = TP["maxi"]
    def cc(s, i): return s * SMS + (i + 0.5) / (maxi.get(s, 400) + 1.0) * SMS
    def pos_of(c):
        s = int(c // SMS); m = maxi.get(s, 400) + 1.0
        return s, int(min(m - 1, max(0, (c - s * SMS) / SMS * m)))
    wins = []
    for W in X["wins"]:
        tape = TP["tapes"].get((W["ses"], W["w"]))
        if not tape: continue
        P = prep_window(W, tape, cc)
        if P is None: continue
        P.cc = cc; P.pos_of = pos_of
        wins.append(P)
    return X, TP, wins, cc, pos_of


def prep_window(W, tape, cc):
    tg = W["trig"]
    s0, i0, j0 = tg["slot"], tg["idx"], tg.get("j", 0)
    k0 = next((n for n, r in enumerate(tape) if (r[0], r[1], r[2]) == (s0, i0, j0)), None)
    if k0 is None: return None
    P = Win(); P.W = W; P.run = W["run"]; P.mint = W["mint"]; P.whale = tg["wallet"]
    P.s0, P.i0 = s0, i0; P.t_trig = tg["t"] / 1e6; P.a_trig = tg["a"]
    P.V0, P.T0 = tg["vsol"], tg["vtok"]
    # outside trades after the trigger with clean states. TOKEN accounting (k = V x T is constant to 6e-9, MEASURED): the clean
    # virtual token reserve = the recorded one + our own tokens bought before (- sold): trades missing from the tape stay inside the
    # recorded states (a SOL-delta walk loses them; FRA r27 had a 4.6 SOL sell missing from the decoded tape)
    P.k_curve = float(P.V0) * float(P.T0)
    out = []; ours_tok = 0
    for r in tape[k0 + 1:]:
        if r[8] in OURS:
            ours_tok += r[5] if r[3] else -r[5]
            continue
        T = float(r[7] + ours_tok)
        out.append((r[0], r[1], r[2], r[3], r[4], r[5], r[8], P.k_curve / T, T))
    P.out = out
    P.key = [x[0] * 100000 + x[1] for x in out]
    P.c = [cc(x[0], x[1]) for x in out]
    # tries
    tries = []
    for a in W["tries"]:
        L = a.get("land") or {}
        landed = L.get("res") not in (None, "unseen") and L.get("slot") is not None and L.get("idx") is not None
        tries.append({"t": a["t"] / 1e6, "slot": a["slot"], "dl": a["deadline"], "vsol": a["vsol"], "vtok": a["vtok"], "min_out": a["min_out"], "spend": a["spend"],
                      "land": (L["slot"], L["idx"]) if landed else None, "rx": (L["first_rx"] / 1e6) if landed and L.get("first_rx") else None,
                      "res": L.get("res"), "sig": a["sig"], "n": a["n"], "client": a.get("client")})
    P.tries = tries
    anc = [tr["rx"] - cc(*tr["land"]) for tr in tries if tr["land"] and tr["rx"]]
    P.off = float(np.median(anc)) if anc else None
    # send slot vs time: send slot ~ floor((t - off_s) / SMS)
    ss = [tr["t"] - tr["slot"] * SMS for tr in tries]
    P.off_s = float(np.median(ss)) - SMS / 2 if ss else None
    # live outcome
    P.fill = W["fills"][0] if W["fills"] else None
    P.fill_rx = None
    if P.fill:
        ft = next((tr for tr in tries if tr["sig"] == P.fill["sig"]), None)
        P.fill_rx = ft["rx"] if ft and ft["rx"] is not None else P.fill["t"] / 1e6
    P.dis = W["dis"]
    P.live_pnl = sum(x["pnl"] or 0 for x in W["real"]) if W["real"] else None
    P.close = W["close"]; P.exit = W["exit"]
    P.sell = W["sells"][0] if W["sells"] else None
    P.en_slot = W["en_slot"]; P.k = W.get("k") or 8; P.spend_live = W.get("spend"); P.live_exit_slots = 2; P.live_exit_ms = 10 ** 9
    # whale's first sell after the trigger (window stop at its arrival + 30 ms)
    P.ws = next((n for n, x in enumerate(out) if x[6] == P.whale and not x[3]), None)
    return P


def state_before(P, s, i):
    """clean curve state just before chain position (s, i)"""
    k = bisect.bisect_left(P.key, s * 100000 + i)
    if k == 0: return float(P.V0), float(P.T0), 0
    x = P.out[k - 1]
    return x[7], x[8], k


def state_at_c(P, c):
    """state after every outside trade with block coordinate < c (index of the next trade)"""
    k = bisect.bisect_left(P.c, c)
    if k == 0: return float(P.V0), float(P.T0), 0
    x = P.out[k - 1]
    return x[7], x[8], k


# ---------------------------------------------------------------------------------------------------------------------
# run-level measured distributions and per-window timing anchors
# ---------------------------------------------------------------------------------------------------------------------
class RunCtx:
    pass


def run_ctx(run, wins, cc):
    R = RunCtx(); R.run = run
    # fill the clock anchors of windows without landed tries from the nearest window in time
    have = sorted((P.t_trig, P.off, P.off_s) for P in wins if P.off is not None and P.off_s is not None)
    ts = [h[0] for h in have]
    for P in wins:
        if P.off is None or P.off_s is None:
            k = min(range(len(ts)), key=lambda q: abs(ts[q] - P.t_trig))
            # the block clock drifts against the feed clock: shift by the slot difference x 212 vs the elapsed time
            P.off, P.off_s = have[k][1], have[k][2]
            P.off_est = True
        else: P.off_est = False
    L = []; nun = 0; nall = 0; Ds = []; Cs = []; taus = []; ws = []; ex = []; qs = []; first = []
    for P in wins:
        for tr in P.tries:
            nall += 1
            if tr["land"] is None: nun += 1; continue
            L.append(cc(*tr["land"]) - (tr["t"] - P.off))
        if P.tries: first.append(P.tries[0]["t"] - P.t_trig)
        if P.fill and P.sell and P.exit:
            Ds.append(cc(P.sell["slot"], P.sell["idx"]) + P.off - P.exit["t"] / 1e6)
            if P.close and P.close.get("held_s"): Cs.append(P.fill["t"] / 1e6 + P.close["held_s"] * 1000 - P.sell["t"] / 1e6)
            if P.exit["why"] == "time-ms": taus.append(P.exit["t"] / 1e6 - P.fill_rx)
        d = P.dis
        if d:
            if d["why"] == "expired": ex.append(d["t"] / 1e6 - (P.off_s + (P.en_slot + 1) * SMS))
            if d["why"] == "whale_sold" and P.ws is not None:
                x = P.out[P.ws]; ws.append(d["t"] / 1e6 - (cc(x[0], x[1]) + P.off))
    R.L = np.array(L); R.p_unseen = nun / max(nall, 1)
    R.D = np.array(Ds) if Ds else np.array([64.0]); R.C = float(np.median(Cs)) if Cs else 500.0
    R.tau = float(np.median(taus)) - 200.0 if taus else 30.0   # runs without a timer exit: the AMS / FRA r28 MEASURED 17..35 ms
    R.b_exp = float(np.median(ex)) if ex else 20.0
    bb = [P.exit["t"] / 1e6 - (cc(P.fill["slot"] + 2, 0) + P.off) for P in wins if P.fill and P.exit and P.exit["why"] == "time-limit"]
    R.b_back = float(np.median(bb)) if len(bb) >= 20 else 36.0   # FRA r27 MEASURED median (148 slot exits)
    R.b_ws = float(np.median(ws)) if ws else 44.0
    R.first = float(np.median(first)) if first else 52.0
    return R


def live_positions(wins):
    """live one-position pauses: [fill seen, close] (ms, feed clock) per filled window"""
    out = []
    for P in wins:
        if P.fill and P.close and P.close.get("held_s"):
            out.append((P.fill["t"] / 1e6, P.fill["t"] / 1e6 + P.close["held_s"] * 1000, id(P)))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# the window replay
# ---------------------------------------------------------------------------------------------------------------------
LIVE_WIN = 10


def full_drop(P):
    """the drop (fraction) if the whale sells its whole balance into the post-trigger curve (arm time)"""
    T = float(P.T0); bal = float(P.W["trig"]["bal"])
    return 1.0 - (T / (T + bal)) ** 2


def window_drop(P, cfg):
    q = cfg.get("quote")
    if q is None: return cfg["drop"]
    alpha, lo, hi = q
    return float(min(hi, max(lo, alpha * full_drop(P))))


def live_qstop(P):
    """the live QUIET stop config of this window's run (N, M) or None"""
    q = (P.W.get("quiet") or {}).get("stop")
    if not q: return None
    a, b = q.split(":"); return int(a), int(b)


def arrival(P, k):
    x = P.out[k]
    t = P.rx_map.get((x[0], x[1], x[2])) if P.rx_map else None
    return t if t is not None else P.c[k] + P.off


def stop_times(P, cfg, R):
    """(t_stop without a fill, en_slot) under cfg; feed clock ms"""
    win = cfg["win"]
    en = int((P.a_trig + 50.0 + win * SMS) // SMS)
    d = P.dis
    if d and d["why"] == "expired" and win == LIVE_WIN: t_exp = d["t"] / 1e6
    else: t_exp = P.off_s + (en + 1) * SMS + R.b_exp
    if d and d["why"] == "whale_sold": t_ws = d["t"] / 1e6
    elif P.ws is not None: t_ws = arrival(P, P.ws) + R.b_ws
    else: t_ws = math.inf
    t_q = math.inf
    qs = cfg.get("qstop")
    if qs:
        N, M = qs
        lq = live_qstop(P)
        dq = (d or {}).get("quiet") or {}
        if lq == (N, M) and d and d["why"] == "quiet": t_q = d["t"] / 1e6
        elif lq == (N, M) and dq.get("decided") and d["why"] != "quiet": t_q = math.inf
        else:
            t_dec = P.off_s + (P.s0 + N) * SMS + R.b_q
            others = 0
            for k, x in enumerate(P.out):
                if arrival(P, k) >= t_dec: break
                if x[6] != P.whale: others += 1
            if others < M: t_q = t_dec
    # the live window was armed at every real try's send time: a rule identical to live had not fired by then
    if P.tries:
        t_alive = P.tries[-1]["t"] + 1e-3
        t_ws = max(t_ws, t_alive)
        if win == LIVE_WIN: t_exp = max(t_exp, t_alive)
        if qs and live_qstop(P) == tuple(qs) and t_q < math.inf: t_q = max(t_q, t_alive)
    return min(t_exp, t_ws, t_q), en


def _in(t, iv):
    for a, b in iv:
        if a <= t < b: return True
    return False


def _phantoms(P, R, a, b, k, en, dl, rng, tag):
    """phantom sends in [a, b): every 212/k ms (random phase), landing L ms later on the block clock (INFERRED)"""
    out = []
    if b <= a: return out
    iv = SMS / (k * R.kratio)
    t = a + rng.random() * iv
    while t < b:
        slot = int((t - P.off_s) // SMS)
        if slot > en: break
        V, T, _ = state_at_c(P, t - P.off)
        if rng.random() < R.p_unseen: land = None; c = None
        else:
            # L >= 5 ms (the ~3% negative measured L are clock noise: a tx cannot land before it is sent); a phantom sent after our live
            # fill was seen lands after it
            c = t - P.off + max(5.0, float(R.L[rng.integers(len(R.L))]))
            if P.fill is not None and t >= P.fill_rx: c = max(c, P.cc(P.fill["slot"], P.fill["idx"]) + 0.01)
            land = P.pos_of(c)
        out.append({"t": t, "slot": slot, "dl": min(slot + dl, en), "vsol": V, "vtok": T, "land": land, "rx": (c + P.off) if c is not None else None,
                    "min_out_live": None, "src": tag})
        t += iv
    return out


def window_sim(P, cfg, R, rng, pause_cf=(), gaps_live=()):
    size = int(round(cfg["size"] * 1e9))
    drop = window_drop(P, cfg)
    t_stop, en = stop_times(P, cfg, R)
    d = P.dis
    t_live_stop = d["t"] / 1e6 if d else (P.tries[-1]["t"] + 1 if P.tries else P.t_trig + R.first)
    t_start = P.tries[0]["t"] if P.tries else P.t_trig + R.first
    live_same_limit = (cfg.get("quote") is None and abs(cfg["drop"] - (P.W.get("drop") or 0.12)) < 1e-12 and size == P.spend_live)
    kk = P.k
    tries = []
    for tr in P.tries:
        if tr["t"] >= t_stop or tr["slot"] > en: continue
        if pause_cf and _in(tr["t"], pause_cf): continue
        if cfg["k"] < kk and (tr["n"] - 1) % (kk // cfg["k"]) != 0: continue
        x = dict(tr); x["dl"] = min(tr["slot"] + cfg["dl"], en); x["src"] = "real"
        x["min_out_live"] = tr["min_out"] if (live_same_limit and cfg["dl"] == 1 and cfg["win"] >= LIVE_WIN) else None
        tries.append(x)
    # phantom periods (INFERRED)
    gaps = []
    if t_stop > t_live_stop: gaps.append((max(t_live_stop, t_start), t_stop))
    for a, b in gaps_live:
        a2, b2 = max(a, t_start), min(b, t_stop, t_live_stop)
        if b2 > a2: gaps.append((a2, b2))
    nph = 0
    for a, b in gaps:
        # minus the cfg pauses
        segs = [(a, b)]
        for pa, pb in pause_cf:
            segs = [s for sg in segs for s in ((sg[0], min(sg[1], pa)), (max(sg[0], pb), sg[1])) if s[1] > s[0]]
        for a2, b2 in segs:
            ph = _phantoms(P, R, a2, b2, cfg["k"], en, cfg["dl"], rng, "ph")
            nph += len(ph); tries += ph
    if cfg["k"] > kk:
        a, b = t_start, min(t_stop, t_live_stop)
        segs = [(a, b)]
        for pa, pb in pause_cf:
            segs = [s for sg in segs for s in ((sg[0], min(sg[1], pa)), (max(sg[0], pb), sg[1])) if s[1] > s[0]]
        for a2, b2 in segs:
            ph = _phantoms(P, R, a2, b2, cfg["k"] - kk, en, cfg["dl"], rng, "phk")
            nph += len(ph); tries += ph
    # fills: the first candidate in chain order
    best = None
    for x in tries:
        if x["land"] is None: continue
        s, i = x["land"]
        if s > x["dl"]: continue
        V, T, kn = state_before(P, s, i)
        mo = x["min_out_live"]
        if mo is None: mo, _ = limit_min_out(x["vsol"], x["vtok"], size, FR, drop)
        tok, xn = buy_out(V, T, size)
        if tok >= mo and (best is None or (s, i) < best[0]):
            best = ((s, i), x, V, T, kn, tok, xn)
    res = {"filled": False, "nph": nph, "drop": drop, "t_stop": t_stop, "pnl": 0.0, "fails": 0}
    if best is None:
        res["fails"] = sum(1 for x in tries if x["land"] is not None)
        res["pnl"] = -res["fails"] * FAIL
        res["n_tries"] = len(tries)
        return res
    (fs, fi), xf, Vb, Tb, kn, tok, xn = best
    t_fill = xf["rx"] if xf["rx"] is not None else P.cc(fs, fi) + P.off
    ex = [x for x in tries if x["t"] < t_fill]
    res["fails"] = sum(1 for x in ex if x["land"] is not None and x is not xf)
    res["n_tries"] = len(ex)
    # ---- exit
    live_fill_try = P.fill is not None and xf.get("sig") == P.fill.get("sig")
    if P.fill and P.exit and P.sell:
        Dw = P.cc(P.sell["slot"], P.sell["idx"]) + P.off - P.exit["t"] / 1e6
        tau = P.exit["t"] / 1e6 - P.fill_rx - 200.0 if P.exit["why"] == "time-ms" else R.tau
    else:
        Dw = float(R.D[rng.integers(len(R.D))]); tau = R.tau
    ex_ = exit_walk(P, kn, Tb, tok, size, t_fill, Dw, tau, cfg, R, rng, live_fill_try, fs)
    gross = ex_["gross"]
    pnl = gross - size - FIX - res["fails"] * FAIL
    why, t_dec, c_sell = ex_["why"], ex_["t_dec"], ex_["c_sell"]
    nsell_hold, nbuy_hold, sell_sol_hold = ex_["nsell"], ex_["nbuy"], ex_["sell_sol"]
    res.update(filled=True, fs=fs, fi=fi, t_fill=t_fill, t_close=t_dec + Dw + R.C, pnl=pnl, gross=gross - size, why=why, src=xf["src"],
               live_try=live_fill_try, p_entry=(Vb + xn) / (Tb - tok), p_pre=Vb / Tb, tok=tok, nsell_hold=nsell_hold, nbuy_hold=nbuy_hold,
               sell_sol_hold=sell_sol_hold, t_dec=t_dec, c_sell=c_sell)
    return res


def run_sim(wins, R, cfg, rep=0, livepos=None):
    """one possible world of a run under cfg (one-position knock-on; window order = trigger time)"""
    livepos = livepos if livepos is not None else live_positions(wins)
    cfpos = []
    out = {}
    for P in wins:
        rng = np.random.default_rng([(cfg(P) or BASE).get("seed", 0) if callable(cfg) else cfg.get("seed", 0), rep, P.W["ses"], P.W["w"], 7])
        t0 = P.t_trig; t1 = P.t_trig + 4000.0
        pc = [(a, b) for a, b, pid in cfpos if b > t0 and a < t1]
        # live pauses of this window that came from EARLIER windows' live positions which do not exist in cfg
        gl = []
        for a, b, pid in livepos:
            if pid == id(P) or not (b > t0 and a < t1): continue
            src = P_by_id.get(pid)
            if src is None or src.t_trig > P.t_trig: continue
            if not any(abs(a - ca) < 1e-6 and pid == cid for ca, cb, cid in cfpos):
                gl.append((a, b))
        c = cfg(P) if callable(cfg) else cfg
        if c is None:
            # SKIP: the window does not arm (no tries, no position)
            out[id(P)] = {"filled": False, "pnl": 0.0, "fails": 0, "nph": 0, "skip": True, "drop": None, "t_stop": None}
            continue
        r = window_sim(P, c, R, rng, pc, gl)
        out[id(P)] = r
        if r["filled"]:
            # a cfg position equal to the live one keeps its live interval (so it is not a gap)
            if r.get("live_try") and P.fill and P.close and P.close.get("held_s"):
                cfpos.append((P.fill["t"] / 1e6, P.fill["t"] / 1e6 + P.close["held_s"] * 1000, id(P)))
            else:
                cfpos.append((r["t_fill"], r["t_close"], id(P)))
    return out


P_by_id = {}


def load(run):
    X, TP, wins, cc, pos_of = prep_run(run)
    R = run_ctx(run, wins, cc)
    lc = X["cfg"][-1]["presend_live"]
    for P in wins:
        P.live_exit_slots = lc.get("exit_slots") or 2
        P.live_exit_ms = lc.get("exit_ms") or 10 ** 9
    for P in wins:
        P_by_id[id(P)] = P
        P.rx_map = {(r[0], r[1], r[2]): r[3] / 1e6 for r in P.W.get("ptape", []) if r[4] not in OURS}
    # the quiet decision bias (live quiet disarms vs the slot-start model)
    q = []
    for P in wins:
        d = P.dis; lq = live_qstop(P)
        if d and d["why"] == "quiet" and lq: q.append(d["t"] / 1e6 - (P.off_s + (P.s0 + lq[0]) * SMS))
    R.b_q = float(np.median(q)) if q else 12.0
    # the effective unique-try rate (MEASURED): FRA's path budget refused ~40% of the sends (rate_path_config), AMS ~3%
    n = 0; dur = 0.0
    for P in wins:
        if len(P.tries) < 2 or not P.dis: continue
        t0 = P.tries[0]["t"]; t1 = P.dis["t"] / 1e6
        if t1 <= t0: continue
        n += sum(1 for tr in P.tries if tr["t"] < t1); dur += t1 - t0
    k_live = lc.get("k") or 8
    R.k_eff = n / dur * SMS if dur > 0 else float(k_live)
    R.kratio = R.k_eff / k_live
    return X, wins, R


def exit_walk(P, kn, Tb, tok, size, t_fill, Dw, tau, cfg, R, rng, live_fill_try, fs):
    """our position from the fill (clean token reserve Tb before our buy of tok tokens) to the sell landing; token accounting"""
    kc = P.k_curve; out = P.out; n = len(out)
    cut = cfg.get("cut", 0.0)
    drop = [bool(out[q][3]) and cut > 0 and rng.random() < cut for q in range(kn, n)] if cut > 0 else None
    t_timer = t_fill + cfg["exit_ms"] + tau
    t_back = P.cc(fs + cfg["exit_slots"], 0) + P.off + R.b_back if cfg.get("exit_slots") else math.inf
    if live_fill_try and P.exit and P.sell:
        # the live decision is known: a live timer exit means the slot backstop had not fired by then; a live slot exit is the backstop;
        # a live TP / SL exit means neither the timer nor the backstop had fired by then
        lt = P.exit["t"] / 1e6
        if P.exit["why"] == "time-ms": t_back = max(t_back, lt + 1e-3)
        elif P.exit["why"] == "time-limit" and cfg.get("exit_slots") == P.live_exit_slots: t_back = lt
        elif P.exit["why"] in ("take-profit", "stop-loss"):
            if cfg.get("exit_slots") == P.live_exit_slots: t_back = max(t_back, lt + 1e-3)
            if cfg["exit_ms"] >= P.live_exit_ms: t_timer = max(t_timer, t_fill + (cfg["exit_ms"] - P.live_exit_ms) + (lt - t_fill) + 1e-3) if P.live_exit_ms < 10 ** 8 else t_timer
    flat = cfg.get("flat")
    t_dec = min(t_timer, t_back)
    why = "time"
    if flat:
        # an outside trade seen before the timer? (the follower cut applies: a dropped buy does not exist)
        any_seen = False; first_after = None
        for q in range(kn, n):
            if drop and drop[q - kn]: continue
            a = arrival(P, q)
            if a < t_timer: any_seen = True; break
            first_after = a; break
        if not any_seen:
            # hold on: sell on the first outside trade seen (TP / SL included), capped at fill + flat ms (the slot backstop off)
            if first_after is not None and first_after <= t_fill + flat: t_dec = first_after; why = "flat_trade"
            else: t_dec = t_fill + flat; why = "flat_cap"
    c_sell = t_dec - P.off + Dw
    tp, sl = cfg["tp"], cfg["sl"]
    T = Tb - tok; drop_tok = 0.0; nsell = nbuy = 0; sell_sol = 0.0; decided = why != "time"
    for q in range(kn, n):
        x = out[q]; c = P.c[q]
        if c >= c_sell: break
        if drop and drop[q - kn]: drop_tok += x[5]; continue
        if x[3]: nbuy += 1
        else: nsell += 1; sell_sol += x[4]
        T = x[8] - tok + drop_tok
        a = arrival(P, q)
        if not decided and a < t_dec:
            V = kc / T
            v = sell_out(V, T, tok) * (1 - FR) / size
            h = "tp" if (tp is not None and v >= 1 + tp) else ("sl" if (sl is not None and v <= 1 - sl) else None)
            if h:
                why = h; decided = True; t_dec = a; c_sell = max(t_dec - P.off + Dw, c + 1e-3)
        elif why == "flat_trade" and not decided and a >= t_dec:
            decided = True
    V = kc / T
    return {"gross": sell_out(V, T, tok) * (1 - FR), "why": why, "t_dec": t_dec, "c_sell": c_sell, "nsell": nsell, "nbuy": nbuy, "sell_sol": sell_sol}


def features(P, H=None):
    """the arm-time features of a window (nothing after the trigger trade)"""
    import datetime
    tg = P.W["trig"]; q = P.W.get("quiet") or {}; v2 = P.W.get("v2") or {}
    f = {"fulldrop": full_drop(P), "wsol": tg["sol"] / 1e9, "pct": tg["pct"], "vsol": tg["vsol"] / 1e9, "age": tg.get("age_slots"), "wh_fol": q.get("wh_fol"),
         "wh_dumps": q.get("wh_dumps"), "since_last": q.get("since_last"), "n_tr_60s": v2.get("n_tr_60s"),
         "hour": (datetime.datetime.fromtimestamp(P.t_trig / 1e3, datetime.UTC) + datetime.timedelta(hours=5)).hour}
    if H is not None:
        h = H.get((P.W["ses"], P.W["w"]))
        if h and h["hist_ok"]: f.update({k: h[k] for k in ("n_big2", "other1", "top_other", "n_hold")})
    return f

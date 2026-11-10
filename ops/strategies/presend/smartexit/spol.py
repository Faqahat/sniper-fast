"""SMARTEXIT policy families.  Every policy is causal: it decides from (a) what the fill record / arm knew at fill time and
(b) other trades on the mint in rx order with rx t <= the decision time.  A policy returns a list of (decision_t_ns, fraction).
Engine TP +20% / SL -20% stay on top of every policy (applied in run_policy).  Event decisions fire at the trigger trade's rx t
+ 0.2 ms; timer decisions at fill + H + 1 ms (slib.timer_t)."""
import itertools
import slib as L

EPS = 200_000   # 0.2 ms processing


def T(f, H): return L.timer_t(f, H)


# ---------- entry features (known at fill time) ----------
def holders(f):
    return ((f.x.get("fann") or {}).get("holders")) or []


def trig_wallet(f):
    return (((f.x.get("arm") or {}).get("trig")) or {}).get("wallet")


def clock_risk(f, P, D, nmin=3):
    """a holder (not the trigger whale) with >= P % of supply whose own history (n >= nmin past holds) says it sells within D slots
    of now: p50 hold - age <= D"""
    tw = trig_wallet(f)
    for h in holders(f):
        if h.get("w") == tw: continue
        if (h.get("pct") or 0) >= P and (h.get("n") or 0) >= nmin and (h.get("p50") or 0) - (h.get("age") or 0) <= D:
            return True
    return False


def whale_clock(f, D, nmin=3):
    tw = trig_wallet(f)
    for h in holders(f):
        if h.get("w") == tw:
            return (h.get("n") or 0) >= nmin and (h.get("p50") or 0) - (h.get("age") or 0) <= D
    return False


# ---------- families ----------
def p_timer(H):
    return lambda f, evs: [(T(f, H), 1.0)]


def p_dyntp(k, m, H):
    """sell at the first seen trade (ms >= m) after which the engine mark >= k; else timer H"""
    def fn(f, evs):
        d = T(f, H)
        for e in evs:
            if e.t >= d: break
            if e.ms >= m and e.mark >= k: return [(e.t + EPS, 1.0)]
        return [(d, 1.0)]
    return fn


def p_stall(N, m, H, need_buy):
    """sell once no outside buy has been seen for N ms (counted from the fill, or from the first follower buy if need_buy),
    not before m ms, at the latest H"""
    def fn(f, evs):
        cap = T(f, H); last = f.t0 if not need_buy else None
        for e in evs:
            if e.t >= cap: break
            if last is not None:
                due = max(last + N * 1e6, f.t0 + m * 1e6)
                if e.t > due: return [(int(due), 1.0)]
            if e.buy: last = e.t
        if last is not None:
            due = max(last + N * 1e6, f.t0 + m * 1e6)
            if due < cap: return [(int(due), 1.0)]
        return [(cap, 1.0)]
    return fn


def p_nbuys(k, m, H):
    """sell when the k-th outside buy after our fill is seen (not before m ms), else H"""
    def fn(f, evs):
        cap = T(f, H); c = 0
        for e in evs:
            if e.t >= cap: break
            if e.buy: c += 1
            if c >= k and e.ms >= m: return [(e.t + EPS, 1.0)]
        return [(cap, 1.0)]
    return fn


def p_bail(X, H, cum, flags):
    """early bail: before timer H, sell on the first seen outside sell >= X SOL (cum: cumulative sells since fill >= X);
    flags: only sells by wallets flagged with any of these letters (B big holder, C creator, I insider, S create-signer)"""
    def fn(f, evs):
        cap = T(f, H); s = 0.0
        for e in evs:
            if e.t >= cap: break
            if e.buy or "O" in e.fl: continue
            if flags and not any(c in e.fl for c in flags): continue
            s = s + e.sol if cum else e.sol
            if s >= X: return [(e.t + EPS, 1.0)]
        return [(cap, 1.0)]
    return fn


def p_extend(H0, W, X, Y, Hmax, N):
    """at H0 hold on only if buy SOL seen in the last W ms >= X and no outside sell >= Y SOL seen since the fill; while holding sell
    on the first seen sell >= Y, or N ms without a buy, or Hmax"""
    def fn(f, evs):
        d0 = T(f, H0)
        seen = [e for e in evs if e.t < d0]
        rb = sum(e.sol for e in seen if e.buy and e.t >= d0 - W * 1e6)
        bigs = any((not e.buy) and e.sol >= Y for e in seen)
        if rb < X or bigs: return [(d0, 1.0)]
        cap = T(f, Hmax); last = max((e.t for e in seen if e.buy), default=f.t0)
        for e in evs:
            if e.t < d0: continue
            if e.t >= cap: break
            if last + N * 1e6 < e.t: return [(int(max(last + N * 1e6, d0)), 1.0)]
            if (not e.buy) and e.sol >= Y: return [(e.t + EPS, 1.0)]
            if e.buy: last = e.t
        due = max(last + N * 1e6, d0)
        return [(int(min(due, cap)), 1.0)]
    return fn


def p_trail(H0, dd, Hmax, kmin):
    """after H0 hold while the mark is >= kmin; sell when it falls dd below its peak (seen marks) or at Hmax"""
    def fn(f, evs):
        d0 = T(f, H0)
        seen = [e for e in evs if e.t < d0]
        mk = seen[-1].mark if seen else None
        if mk is None or mk < kmin: return [(d0, 1.0)]
        peak = max(e.mark for e in seen); cap = T(f, Hmax)
        for e in evs:
            if e.t < d0: continue
            if e.t >= cap: break
            peak = max(peak, e.mark)
            if e.mark <= peak - dd: return [(e.t + EPS, 1.0)]
        return [(cap, 1.0)]
    return fn


def p_clock(P, D, Hr, Hs):
    """entry-conditioned timer: Hr if a holder clock says a >= P % holder is due to sell within D slots, else Hs"""
    return lambda f, evs: [(T(f, Hr if clock_risk(f, P, D) else Hs), 1.0)]


def p_kind(Ht2, Hra):
    return lambda f, evs: [(T(f, Ht2 if f.kind == "t2" else Hra), 1.0)]


def p_partial(a, H1, H2):
    return lambda f, evs: [(T(f, H1), a), (T(f, H2), 1 - a)]


def p_watch(H0, Hw, flag):
    """hold to Hw if a flagged-wallet (W watched follower bot) buy was seen before H0, else H0"""
    def fn(f, evs):
        d0 = T(f, H0)
        if any(e.buy and flag in e.fl and "O" not in e.fl for e in evs if e.t < d0): return [(T(f, Hw), 1.0)]
        return [(d0, 1.0)]
    return fn


def run_policy(f, evs, fn, fc=0.0, lag=None):
    """apply engine TP/SL on top of the policy's decisions and settle.  Returns net SOL"""
    dec = fn(f, evs)
    out = []; start = 0.0
    for n, (d, fr) in enumerate(dec):
        d2, why = L.with_tpsl(evs, d, start)
        if why != "time":            # TP/SL sells everything left
            out.append((d2, 1.0 - sum(a for _, a in out))); break
        out.append((d2, fr)); start = (d2 - f.t0) / 1e6
    return L.settle(f, out, fc, lag)[0]


def grid():
    """(family, params, fn) for the DEV search"""
    G = []
    for H in (75, 100, 110, 125, 140, 150, 160, 175, 200, 250, 300):
        G.append(("timer", (H,), p_timer(H)))
    for k, m, H in itertools.product((1.02, 1.04, 1.06, 1.08, 1.10, 1.13, 1.16), (0, 25, 50, 75, 100), (125, 160, 200, 300)):
        G.append(("dyntp", (k, m, H), p_dyntp(k, m, H)))
    for N, m, H, nb in itertools.product((25, 40, 60, 80, 120), (50, 75, 100, 125), (160, 200, 300, 500), (False, True)):
        G.append(("stall", (N, m, H, nb), p_stall(N, m, H, nb)))
    for k, m, H in itertools.product((1, 2, 3, 4, 6), (0, 50, 100), (125, 160, 200)):
        G.append(("nbuys", (k, m, H), p_nbuys(k, m, H)))
    for X, H, cum, fl in itertools.product((0.5, 1.0, 2.0, 3.0, 5.0), (125, 160, 200, 300), (False, True), ("", "BCIS", "B", "CIS")):
        G.append(("bail", (X, H, cum, fl), p_bail(X, H, cum, fl)))
    for H0, W, X, Y, Hmax, N in itertools.product((125, 160), (50, 125), (0.5, 1.0, 2.0, 4.0), (0.5, 1.0, 3.0), (300, 600, 1000, 2000), (50, 100, 200)):
        G.append(("extend", (H0, W, X, Y, Hmax, N), p_extend(H0, W, X, Y, Hmax, N)))
    for H0, dd, Hmax, kmin in itertools.product((125, 160), (0.02, 0.04, 0.08), (300, 600, 1000, 2000), (1.0, 1.05, 1.10)):
        G.append(("trail", (H0, dd, Hmax, kmin), p_trail(H0, dd, Hmax, kmin)))
    for P, Dd, Hr, Hs in itertools.product((1.0, 2.0, 4.0), (0, 3, 10, 30), (75, 100, 125), (125, 160, 200)):
        if Hr < Hs: G.append(("clock", (P, Dd, Hr, Hs), p_clock(P, Dd, Hr, Hs)))
    for a, b in itertools.product((100, 125, 160, 200), (100, 125, 160, 200)):
        G.append(("kind", (a, b), p_kind(a, b)))
    for a, H1, H2 in itertools.product((0.3, 0.5, 0.7), (75, 100, 125), (160, 200, 300, 600)):
        G.append(("partial", (a, H1, H2), p_partial(a, H1, H2)))
    for H0, Hw in itertools.product((125, 160), (200, 300, 600, 1000)):
        G.append(("watch", (H0, Hw, "W"), p_watch(H0, Hw, "W")))
    return G


# ---------- refinements (added after the first DEV grid) ----------
def clock_hz(f, P, z):
    tw = trig_wallet(f)
    return any(h.get("w") != tw and (h.get("pct") or 0) >= P and (h.get("hz3") or 0) >= z for h in holders(f))


def p_clockz(P, z, Hr, Hs):
    return lambda f, evs: [(T(f, Hr if clock_hz(f, P, z) else Hs), 1.0)]


def p_clockw(Dd, Hr, Hs):
    return lambda f, evs: [(T(f, Hr if whale_clock(f, Dd) else Hs), 1.0)]


def p_clock_ext(P, Dd, Hr, Hs, W, X, Y, Hmax, N):
    """clock timer; on the safe path (Hs) the extend rule from Hs"""
    ext = p_extend(Hs, W, X, Y, Hmax, N)
    def fn(f, evs):
        if clock_risk(f, P, Dd): return [(T(f, Hr), 1.0)]
        return ext(f, evs)
    return fn


def run_policy_lag(f, evs, fn, lagfn, fc=0.0):
    """like run_policy, but each part's lag = lagfn(f, decision_t) (resampled rows)"""
    import slib as L
    dec = fn(f, evs)
    out = []; start = 0.0
    for d, fr in dec:
        d2, why = L.with_tpsl(evs, d, start)
        if why != "time":
            out.append((d2, 1.0 - sum(a for _, a in out))); break
        out.append((d2, fr)); start = (d2 - f.t0) / 1e6
    # settle part by part with its own drawn lag
    sold = []; g = 0; rem = f.q
    for n, (d, fr) in enumerate(out):
        tok = rem if n == len(out) - 1 else int(f.q * fr)
        rem -= tok
        land = d + lagfn(f, d) * 1e6
        if (land - f.t0) / 1e6 > L.TAPE_MS: land = f.t0 + int((L.TAPE_MS - 0.001) * 1e6)
        vsol, vtok = f.state(land, fc, sold)
        g += L.gross_out(tok, vsol, vtok); sold.append((land, tok))
    return f.real + (g - f.g_real) * (1 - L.FEE) / 1e9 - L.SELL_TX * (len(out) - 1)

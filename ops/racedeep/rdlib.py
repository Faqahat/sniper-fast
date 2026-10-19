# READ-ONLY racedeep helpers: load U.pkl, realistic sim from an arbitrary landing time, landing models, stats.
import pickle, bisect, math, statistics as st
K = 30.0 * 1.073e9
FEE, SLIP, PRIO_BUY, PRIO_SELL = 0.0125, 1.03, 0.009, 0.001
SLOT = 217.0


def load(path="/root/racedeep/U.pkl"):
    U = pickle.load(open(path, "rb"))
    for o in U:
        o["pt"] = [p[0] for p in o["path"]]
        o["pv"] = [p[1] / 1e9 for p in o["path"]]
        o["base9"] = o["base"] / 1e9
    return U


def land_time(o, j, mode):
    """landing time (ms after create) for a trigger at trade index j (j=-1 -> the create itself).
    mode: ('S', D) -> D non-vote txs after the trigger in S if room, else S+1 at q=0.5;
          ('S1', q) -> slot after the trigger's slot, behind fraction q of that slot's trades."""
    if j < 0:
        t, k, d = 0.0, 0, 0
    else:
        z = o["tr"][j]
        t, k, d = z[0], z[1], z[2]
    kind, p = mode
    if kind == "S":
        if k == 0 and d + p <= o["rem"]:
            return (d + p) * o["mpt"] + 1e-6
        kind, p = "S1", 0.5
    # next slot after slot k
    return o["tS"] + k * SLOT + p * SLOT + 1e-6


def sim(o, t0, ex, size=2.0):
    """realistic PnL fraction. ex: dict(T=ms, legs=[(frac, tp_mult)], trail=f, part_at=(ms, frac), sl=f)"""
    pt, pv = o["pt"], o["pv"]
    i = bisect.bisect_right(pt, t0) - 1
    v0 = pv[max(i, 0)]
    ve = v0 * math.sqrt(SLIP)
    s_in = size * (1 - FEE)
    tok = K / ve - K / (ve + s_in)
    st_ = dict(left=1.0, net=s_in, proc=0.0, ns=0)

    def sell(frac, v):
        frac = min(frac, st_["left"])
        if frac <= 1e-9:
            return
        vq = v + st_["net"]
        out = vq - K / (K / vq + tok * frac)
        st_["net"] -= out
        st_["proc"] += out * (1 - FEE)
        st_["left"] -= frac
        st_["ns"] += 1
    T = ex["T"]
    legs = sorted(ex.get("legs") or [], key=lambda z: z[1])
    tr, pa, sl = ex.get("trail"), ex.get("part_at"), ex.get("sl")
    simple = not legs and not tr and not pa and not sl
    if simple:
        k = bisect.bisect_right(pt, t0 + T) - 1
        sell(1.0, pv[max(k, i, 0)])
    else:
        vx, peak, pa_done = v0, 0.0, False
        for k in range(i + 1, len(pt)):
            if pt[k] - t0 > T:
                break
            vx = pv[k]
            rr = (vx / ve) ** 2
            peak = max(peak, rr)
            if pa and not pa_done and pt[k] - t0 >= pa[0]:
                pa_done = True
                sell(pa[1], vx)
            while legs and rr >= legs[0][1] and st_["left"] > 1e-9:
                f, _ = legs.pop(0)
                sell(f, vx)
            if st_["left"] <= 1e-9:
                break
            if (sl and rr <= sl) or (tr and peak >= 1.1 and rr <= peak * tr and (not pa or pa_done)):
                sell(st_["left"], vx)
                break
        if st_["left"] > 1e-9:
            sell(st_["left"], vx)
    return (st_["proc"] - size - PRIO_BUY - PRIO_SELL * st_["ns"]) / size


def pf(o, t):
    """price/floor at time t (after every trade at <= t)"""
    i = bisect.bisect_right(o["pt"], t) - 1
    return (o["pv"][max(i, 0)] / o["base9"]) ** 2


def stats(v):
    if not v:
        return dict(n=0, avg=float("nan"), med=float("nan"), ex3=float("nan"), win=float("nan"))
    s = sorted(v)
    ex = s[:-3] if len(s) > 3 else s[:0]
    return dict(n=len(v), avg=st.mean(v), med=st.median(v), ex3=st.mean(ex) if ex else float("nan"), win=sum(x > 0 for x in v) / len(v))


def fmt(s):
    if not s["n"]:
        return "n=0"
    return f"n={s['n']:4} avg {s['avg']:+6.1%} med {s['med']:+6.1%} ex3 {s['ex3']:+6.1%} win {s['win']:4.0%}"


EXITS = {
    "t0.5": dict(T=500), "t1": dict(T=1000), "t2": dict(T=2000), "t3": dict(T=3000), "t5": dict(T=5000), "t10": dict(T=10000),
    "half1s+trail0.8/40s": dict(T=40000, part_at=(1000, 0.5), trail=0.8),
    "70%1s+trail0.8/40s": dict(T=40000, part_at=(1000, 0.7), trail=0.8),
    "half@1.3 half@2 /10s": dict(T=10000, legs=[(0.5, 1.3), (0.5, 2.0)]),
    "trail0.8/40s": dict(T=40000, trail=0.8),
    "tp1.3/5s": dict(T=5000, legs=[(1.0, 1.3)]),
}

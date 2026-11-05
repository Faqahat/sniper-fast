#!/usr/bin/env python3
"""SMARTEXIT step 7 (DEV ONLY): plateaus around the step-4 leaders + clock variants + combos, and robustness rows for a shortlist.
Rows per policy: gain vs exact t125 (own lag), w/o top-5 gains, fc20, per-run-pool resampled lag (10 draws), phase-conditioned
resampled lag (10 draws; the baseline gets the same treatment), DEV chunks positive."""
import sys, json, collections, itertools, random, multiprocessing as mp
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/smartexit")
import slib as L, spol as P

F, J, _ = L.load_fills(("dev",))
H = J["split_hours"]["dev"]
r42 = sorted(f.t0 for f in F if f.run == 42); mid42 = r42[len(r42) // 2]
CH = [f"r{f.run}" if f.run != 42 else ("r42a" if f.t0 < mid42 else "r42b") for f in F]
EV0 = [L.events(f) for f in F]; EV2 = [L.events(f, 0.2) for f in F]
base0 = [P.run_policy(f, e, P.p_timer(125)) for f, e in zip(F, EV0)]
base2 = [P.run_policy(f, e, P.p_timer(125), 0.2) for f, e in zip(F, EV2)]

def core(fn):
    p0 = [P.run_policy(f, e, fn) for f, e in zip(F, EV0)]
    p2 = [P.run_policy(f, e, fn, 0.2) for f, e in zip(F, EV2)]
    d0 = [a - b for a, b in zip(p0, base0)]; d2 = [a - b for a, b in zip(p2, base2)]
    byc = collections.defaultdict(float)
    for c, g in zip(CH, d0): byc[c] += g
    s = sorted(d0, reverse=True)
    return dict(gain=sum(d0), wo5=sum(s[5:]), fc20=sum(d2), npos=sum(1 for v in byc.values() if v > 1e-9),
                nch=sum(1 for v in byc.values() if abs(v) > 1e-9), chunks=dict(byc))

def robust(fn, draws=10):
    PL = L.PhaseLag(F)
    rs_b = rs_p = ph_b = ph_p = 0.0
    for k in range(draws):
        rnd = random.Random(100 + k)
        for f, e in zip(F, EV0):
            lg = f.lags_pool[rnd.randrange(len(f.lags_pool))]
            rs_b += P.run_policy(f, e, P.p_timer(125), lag=lg); rs_p += P.run_policy(f, e, fn, lag=lg)
        PL.rnd = random.Random(200 + k)
        st = PL.rnd.getstate()
        for f, e in zip(F, EV0):
            ph_b += P.run_policy_lag(f, e, P.p_timer(125), PL.draw)
        PL.rnd.setstate(st)
        for f, e in zip(F, EV0):
            ph_p += P.run_policy_lag(f, e, fn, PL.draw)
    return dict(rs=(rs_p - rs_b) / draws, ph=(ph_p - ph_b) / draws)

FAM = []
for P_, Dd, Hr, Hs in itertools.product((0.5, 1, 2, 4, 6), (-10, -5, 0, 3, 10), (50, 75, 100, 125), (140, 150, 160, 175)):
    FAM.append(("clock", (P_, Dd, Hr, Hs), P.p_clock(P_, Dd, Hr, Hs)))
for P_, z, Hr, Hs in itertools.product((1, 2, 4), (0.05, 0.1, 0.2, 0.3), (75, 100), (150, 160)):
    FAM.append(("clockz", (P_, z, Hr, Hs), P.p_clockz(P_, z, Hr, Hs)))
for Dd, Hr, Hs in itertools.product((-5, 0, 3, 10, 30), (75, 100, 125), (150, 160)):
    FAM.append(("clockw", (Dd, Hr, Hs), P.p_clockw(Dd, Hr, Hs)))
for W, X, Y, Hmax, N in itertools.product((50, 100, 125), (0.5, 1.0, 1.5, 2.0), (0.5, 1.0, 2.0, 3.0), (300, 500), (25, 50, 75)):
    FAM.append(("extend160", (160, W, X, Y, Hmax, N), P.p_extend(160, W, X, Y, Hmax, N)))
for (P_, Dd, Hr), (W, X, Y, N) in itertools.product(((1, 0, 75), (1, 0, 100), (2, 0, 100), (4, 0, 75)), ((125, 1.0, 1.0, 50), (50, 0.5, 3.0, 50), (100, 1.0, 1.0, 50))):
    FAM.append(("clock_ext", (P_, Dd, Hr, 160, W, X, Y, 300, N), P.p_clock_ext(P_, Dd, Hr, 160, W, X, Y, 300, N)))

def ev(i):
    fam, prm, fn = FAM[i]; r = core(fn); r.update(fam=fam, prm=prm); return r

if __name__ == "__main__":
    print(f"DEV fills {len(F)} hours {H:.1f} base {sum(base0):+.3f} fc20 {sum(base2):+.3f}; variants {len(FAM)}", flush=True)
    # how many fills each clock flags
    for P_, Dd in ((1, 0), (2, 0), (4, 0), (1, -5), (1, 10)):
        n = sum(1 for f in F if P.clock_risk(f, P_, Dd)); print(f"  clock_risk P{P_} D{Dd}: {n} fills ({n / len(F):.0%})")
    with mp.Pool(14) as pool: R = pool.map(ev, range(len(FAM)), chunksize=4)
    for r in R: r["score"] = min(r["gain"], r["wo5"], r["fc20"])
    byf = collections.defaultdict(list)
    for r in R: byf[r["fam"]].append(r)
    for fam, rs in byf.items():
        rs.sort(key=lambda r: -r["score"])
        print(f"\n== {fam} ({len(rs)}) top 8 by min(gain, wo5, fc20):")
        for r in rs[:8]:
            print(f"  {str(r['prm']):44} gain {r['gain']:+.3f} wo5 {r['wo5']:+.3f} fc20 {r['fc20']:+.3f} chunks+ {r['npos']}/{r['nch']}")
    # clock plateau table (gain / fc20) Hr x Hs at P=1, D=0 and P x D at Hr 100, Hs 160
    look = {(r["fam"], r["prm"]): r for r in R}
    print("\nclock plateau P=1 D=0 (gain/fc20): rows Hr, cols Hs 140/150/160/175")
    for Hr in (50, 75, 100, 125):
        print(f"  Hr {Hr:3}: " + "  ".join(f"{look[('clock', (1, 0, Hr, Hs))]['gain']:+.2f}/{look[('clock', (1, 0, Hr, Hs))]['fc20']:+.2f}" for Hs in (140, 150, 160, 175)))
    print("clock plateau Hr=100 Hs=160 (gain/fc20): rows P, cols D -10/-5/0/3/10")
    for P_ in (0.5, 1, 2, 4, 6):
        print(f"  P {P_:3}: " + "  ".join(f"{look[('clock', (P_, Dd, 100, 160))]['gain']:+.2f}/{look[('clock', (P_, Dd, 100, 160))]['fc20']:+.2f}" for Dd in (-10, -5, 0, 3, 10)))
    json.dump(R, open(f"{L.D}/dev_refine.json", "w"))
    # robustness rows for a shortlist
    SL = [("timer160", P.p_timer(160)), ("timer150", P.p_timer(150)),
          ("clock 1/0/100/160", P.p_clock(1, 0, 100, 160)), ("clock 1/0/75/160", P.p_clock(1, 0, 75, 160)),
          ("extend 160/125/1/1/300/50", P.p_extend(160, 125, 1.0, 1.0, 300, 50)),
          ("clock_ext 1/0/100/160 +125/1/1/300/50", P.p_clock_ext(1, 0, 100, 160, 125, 1.0, 1.0, 300, 50))]
    print("\nshortlist robustness (DEV): gain own | fc20 | resampled lag | phase lag")
    for nm, fn in SL:
        c = core(fn); r = robust(fn)
        print(f"  {nm:40} {c['gain']:+.3f} ({c['gain'] / H * 24:+.2f}/d) | wo5 {c['wo5']:+.3f} | fc20 {c['fc20']:+.3f} | rs {r['rs']:+.3f} | ph {r['ph']:+.3f} | chunks+ {c['npos']}/{c['nch']}", flush=True)

#!/usr/bin/env python3
"""SMARTEXIT step 8: score the FROZEN policies vs exact t125 on the SAME fills, per split and per run.
Refuses to run if any script's sha256 differs from FROZEN.json.  usage: s8_score.py dev|val|hold|all
Rows: own lag (SOL, SOL/day, win%, w/o top5, gain, gain w/o top-5 gains, 95% bootstrap CI of the gain, fills up/down),
fc20 (followers -20%), resampled lag (10 draws from the run's own lags), phase lag (10 draws, lag conditioned on the decision's
phase in its slot).  Per run: n, t125 SOL, gain own, gain fc20.
SOL/day uses covered hours = run hours x share of the run's fills that have a hold tape."""
import sys, json, hashlib, collections, random
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/smartexit")
import slib as L, spol as P
C = "/home/it/sniper/ops/strategies/presend/smartexit"
FZ = json.load(open(f"{C}/FROZEN.json"))
for fn, h in FZ["sha256"].items():
    if hashlib.sha256(open(f"{C}/{fn}", "rb").read()).hexdigest() != h:
        sys.exit(f"ABORT: {fn} changed since freeze")

def build(spec):
    return getattr(P, spec["fn"])(*spec["args"])

POL = [(p["name"], build(p)) for p in FZ["policies"]]
BASE = P.p_timer(125)
which = sys.argv[1] if len(sys.argv) > 1 else "all"
splits = ("dev", "val", "hold") if which == "all" else (which,)
J = json.load(open(f"{L.D}/fills.json"))
nf = collections.Counter(x["run"] for x in J["fills"]); nt = collections.Counter(x["run"] for x in J["fills"] if x.get("tape"))
def cov_hours(sp, fills):
    """r42 is split at 11-01 12:00 PKT by s1_load (split_hours); r42 tape coverage is 1327/1328 so no share applied"""
    rh = {int(k): v for k, v in J["run_hours"].items()}
    share = {r: (nt[r] / nf[r] if nf[r] else 0) for r in rh}
    if sp == "val": return J["split_hours"]["val"]
    if sp == "dev": return sum(rh[r] * share[r] for r in range(37, 42)) + (J["split_hours"]["dev"] - sum(rh[r] for r in range(37, 42)))
    return sum(rh[r] * share[r] for r in rh if r >= 43)

ALLF, _, _ = L.load_fills()
PL = L.PhaseLag(ALLF)       # measured lag-by-phase from every real exit (a physical property, not tuned)
OUT = {}
for sp in splits:
    F = [f for f in ALLF if f.split == sp]
    hrs = cov_hours(sp, F)
    E0 = [L.events(f) for f in F]; E2 = [L.events(f, 0.2) for f in F]
    b0 = [P.run_policy(f, e, BASE) for f, e in zip(F, E0)]; b2 = [P.run_policy(f, e, BASE, 0.2) for f, e in zip(F, E2)]
    res = {}
    for nm, fn in [("t125 (baseline)", BASE)] + POL:
        p0 = [P.run_policy(f, e, fn) for f, e in zip(F, E0)]; p2 = [P.run_policy(f, e, fn, 0.2) for f, e in zip(F, E2)]
        g = [a - b for a, b in zip(p0, b0)]; gs = sorted(g, reverse=True); ps = sorted(p0, reverse=True)
        rs = ph = 0.0
        for k in range(10):
            rnd = random.Random(100 + k)
            for f, e in zip(F, E0):
                lg = f.lags_pool[rnd.randrange(len(f.lags_pool))]
                rs += P.run_policy(f, e, fn, lag=lg) - P.run_policy(f, e, BASE, lag=lg)
            PL.rnd = random.Random(200 + k); st = PL.rnd.getstate()
            for f, e in zip(F, E0): ph -= P.run_policy_lag(f, e, BASE, PL.draw)
            PL.rnd.setstate(st)
            for f, e in zip(F, E0): ph += P.run_policy_lag(f, e, fn, PL.draw)
        byrun = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
        for f, a, b, c, d in zip(F, p0, b0, p2, b2):
            v = byrun[f.run]; v[0] += 1; v[1] += b; v[2] += a - b; v[3] += c - d
        res[nm] = dict(n=len(F), sol=sum(p0), day=sum(p0) / hrs * 24, win=sum(1 for a in p0 if a > 0) / len(F), wo5=sum(ps[5:]),
                       gain=sum(g), gain_day=sum(g) / hrs * 24, gain_wo5=sum(gs[5:]), ci=L.boot_ci(g),
                       up=sum(1 for a in g if a > 1e-9), down=sum(1 for a in g if a < -1e-9),
                       fc20_sol=sum(p2), fc20_gain=sum(p2) - sum(b2), rs_gain=rs / 10, ph_gain=ph / 10,
                       byrun={r: v for r, v in sorted(byrun.items())})
    OUT[sp] = dict(hours=hrs, res=res)
    print(f"\n===== {sp.upper()}: fills {len(F)}, covered hours {hrs:.1f}")
    print(f"  {'policy':34} {'SOL':>8} {'/day':>7} {'win%':>5} {'w/o5':>8} | {'gain':>7} {'/day':>6} {'g w/o5':>7} {'95% CI':>17} {'up/down':>9} | {'fc20 SOL':>8} {'fc20 g':>7} | {'rs g':>7} {'ph g':>7}")
    for nm, r in res.items():
        print(f"  {nm:34} {r['sol']:+8.3f} {r['day']:+7.2f} {r['win'] * 100:5.1f} {r['wo5']:+8.3f} | {r['gain']:+7.3f} {r['gain_day']:+6.2f} "
              f"{r['gain_wo5']:+7.3f} [{r['ci'][0]:+.2f},{r['ci'][1]:+.2f}] {r['up']:4}/{r['down']:<4} | {r['fc20_sol']:+8.3f} {r['fc20_gain']:+7.3f} | {r['rs_gain']:+7.3f} {r['ph_gain']:+7.3f}")
    print("  per run (n, t125 SOL | gain own / fc20 per policy):")
    runs = sorted(res["t125 (baseline)"]["byrun"])
    for r in runs:
        v = res["t125 (baseline)"]["byrun"][r]
        print(f"   r{r}: n {v[0]:4} t125 {v[1]:+7.3f} | " + " | ".join(f"{nm.split()[0]} {res[nm]['byrun'][r][2]:+.3f}/{res[nm]['byrun'][r][3]:+.3f}" for nm, _ in POL))
json.dump(OUT, open(f"{L.D}/score_{which}.json", "w"), default=str)

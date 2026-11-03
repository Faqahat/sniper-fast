#!/usr/bin/env python3
"""SPEED35 step 5: calibration (sim 'cur' vs live) and the extra-SOL tables (paired per window vs 'cur'), bootstrap 90% CI,
without the top 5 windows, peak/off-peak (PKT hours with above-median armed windows per hour). Out: stdout + speed35/tables.txt"""
import pickle, datetime, collections, numpy as np
D = "/home/moiz/sniper-data/speed35"
R = pickle.load(open(f"{D}/replay.pkl", "rb"))
pkt = lambda t: datetime.datetime.fromtimestamp(t / 1e9, datetime.UTC) + datetime.timedelta(hours=5)
H = {}
for rn in ("r36", "r37"):
    t = [r["t"] for r in R if r["run"] == rn]; H[rn] = (max(t) - min(t)) / 3.6e12
hrs = sum(H.values())
L = []
def p(s=""): print(s); L.append(s)
p(f"windows {len(R)} hours r36 {H['r36']:.1f} r37 {H['r37']:.1f}")
p("CALIBRATION (sim current landing vs live, same windows): run | live fills | sim exp fills | live P&L | sim P&L | sim P&L -20% followers")
for rn in ("r36", "r37", "both"):
    S = [r for r in R if rn == "both" or r["run"] == rn]
    for key in (("cur", "cur"), ("young-ref", "young-ref")):
        p(f"  {rn:4s} {key[0]:9s} | {sum(r['lf'] > 0 for r in S)} | {sum(r['res'][key][1] for r in S):.1f} | {sum(r['lp'] for r in S):+.3f} | "
          f"{sum(r['res'][key][0] for r in S):+.3f} | {sum(r['res'][key][2] + (r['res'][key][0] - r['res'][key][0]) for r in S):+.3f}")
# peak hours
cnt = collections.Counter(pkt(r["t"]).hour for r in R)
hcov = collections.Counter()
for rn in ("r36", "r37"):
    t = sorted(r["t"] for r in R if r["run"] == rn); h0 = pkt(t[0]); h1 = pkt(t[-1])
    x = h0.replace(minute=0, second=0, microsecond=0)
    while x <= h1: hcov[x.hour] += 1; x += datetime.timedelta(hours=1)
rate = {h: cnt[h] / hcov[h] for h in hcov if hcov[h]}
med = np.median(list(rate.values())); PEAK = {h for h, v in rate.items() if v > med}
p(f"peak PKT hours (armed windows/h above median {med:.0f}): {sorted(PEAK)}")
rng = np.random.default_rng(7)
def stats(S, key):
    d = np.array([r["res"][key][0] - r["res"][("cur", "cur")][0] for r in S]); df = np.array([r["res"][key][1] - r["res"][("cur", "cur")][1] for r in S])
    dc = np.array([r["res"][key][2] - r["res"][("cur", "cur")][2] for r in S])
    bs = [d[rng.integers(0, len(d), len(d))].sum() for _ in range(4000)]
    top = np.sort(d)[::-1][:5].sum()
    return d.sum(), dc.sum(), df.sum(), np.percentile(bs, [5, 95]), d.sum() - top
p("")
p("EXTRA vs current landing (SOL over r36+r37, paired per window). buy=try landing model, sell=sell landing model")
p("| buy landing | sell landing | extra SOL | per day @0.696 | -20% followers extra | fills added | mSOL per added fill | 90% CI | w/o top 5 | peak | off-peak |")
for key in [k for k in R[0]["res"] if k[0] not in ("cur", "young-ref")]:
    a, c, f, ci, nt = stats(R, key)
    pk = stats([r for r in R if pkt(r["t"]).hour in PEAK], key)[0]; op = stats([r for r in R if pkt(r["t"]).hour not in PEAK], key)[0]
    p(f"| {key[0]} | {'unchanged' if key[1] == 'cur' else 'same factor'} | {a:+.3f} | {a / hrs * 24:+.2f} | {c:+.3f} | {f:+.1f} | "
      f"{(a / f * 1000) if abs(f) > 0.5 else float('nan'):+.1f} | [{ci[0]:+.2f}, {ci[1]:+.2f}] | {nt:+.3f} | {pk:+.3f} | {op:+.3f} |")
p("")
p("per run extra (prop35, both legs):")
for rn in ("r36", "r37"):
    S = [r for r in R if r["run"] == rn]; a, c, f, ci, nt = stats(S, ("prop35", "prop35"))
    p(f"  {rn}: {a:+.3f} SOL ({a / H[rn] * 24:+.2f}/day) fills {f:+.1f} CI [{ci[0]:+.2f}, {ci[1]:+.2f}]")
open(f"{D}/tables.txt", "w").write("\n".join(L) + "\n")

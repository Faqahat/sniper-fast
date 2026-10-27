#!/usr/bin/env python3
"""HAQQ_SEL step 6 (read-only): regular-dip (M2) scenario tables from m2_rows.pkl (h4_m2.py).
  ideal : the 35 ms landing row (the fastest the replay models; guard-blocked buys stay failures: the dip was gone)
  50/30%: each 35 ms fill lands with p, else a failed buy (FAIL 0.0005)
  50 ms / 75 ms rows: the replay's slower landing rows (our measured live landing median is ~58 ms; shown per row)
Ranges: 5-95% of 4000 bootstrap resamples of the engine's attempts. Main = AMS (one engine, the live regular setup); FRA+AMS aside."""
import pickle, json
import numpy as np
DATA = "/home/moiz/sniper-data/haqq_sel"
Z = pickle.load(open(f"{DATA}/m2_rows.pkl", "rb"))
FAIL = 0.0005
rng = np.random.default_rng(5)
NB = 4000


def boot(vals, p=None, fills=None):
    vals = np.asarray(vals, float); n = len(vals)
    if n == 0: return 0.0, 0.0, 0.0, 0.0
    tot = []
    for _ in range(NB):
        ix = rng.integers(0, n, n)
        if p is None: tot.append(vals[ix].sum())
        else:
            f = fills[ix]; land = f & (rng.random(n) < p)
            tot.append(np.where(land, vals[ix], -FAIL).sum())
    tot = np.array(tot)
    return float(np.percentile(tot, 5)), float(np.percentile(tot, 95)), float((tot > 0).mean()), float(tot.mean())


out = {}; lines = []
for srv in ("a", "f+a"):
    for nm in ("HQ", "ALL", "NONHQ", "HQKNOWN", "NOTKNOWN", "HQSPAN"):
        r35 = Z[(nm, srv, 35)]
        v = np.array([p for _, _, p, f in r35["rows"]]); f = np.array([bool(f) for _, _, p, f in r35["rows"]])
        res = {}
        lo, hi, pos, _ = boot(v); res["ideal"] = dict(att=r35["att"], fills=int(f.sum()), pnl=float(v.sum()), lo=lo, hi=hi, pos=pos, per_fill=float(v[f].mean()) if f.any() else 0)
        for lab, p in (("p50", 0.5), ("p30", 0.3)):
            exp = float((v * f).sum() * p + (-FAIL) * (f.sum() * (1 - p) + (~f).sum()))
            lo, hi, pos, _ = boot(v, p, f); res[lab] = dict(fills=float(f.sum() * p), pnl=exp, lo=lo, hi=hi, pos=pos)
        for lat in (50, 75):
            rr = Z[(nm, srv, lat)]; vv = np.array([p for _, _, p, f in rr["rows"]]); ff = np.array([bool(f) for _, _, p, f in rr["rows"]])
            lo, hi, pos, _ = boot(vv); res[f"l{lat}"] = dict(att=rr["att"], fills=int(ff.sum()), pnl=float(vv.sum()), lo=lo, hi=hi, pos=pos,
                                                            per_fill=float(vv[ff].mean()) if ff.any() else 0)
        out[f"{nm}|{srv}"] = res
        lines.append(f"### M2 {nm} ({srv}): {r35['att']} picks tried at 35 ms, {int(f.sum())} fill, {int((~f).sum())} guard-blocked")
        lines.append("| Scenario | Fills | P&L SOL | 5-95% | P(>0) | Per fill |"); lines.append("|---|---|---|---|---|---|")
        x = res["ideal"]; lines.append(f"| (a) ideal (35 ms row) | {x['fills']} | {x['pnl']:+.2f} | {x['lo']:+.2f} to {x['hi']:+.2f} | {100 * x['pos']:.0f}% | {x['per_fill']:+.4f} |")
        for lab, nm2 in (("p50", "(b) 50% land"), ("p30", "(c) 30% land")):
            x = res[lab]; lines.append(f"| {nm2} | {x['fills']:.0f} | {x['pnl']:+.2f} | {x['lo']:+.2f} to {x['hi']:+.2f} | {100 * x['pos']:.0f}% | |")
        for lat in (50, 75):
            x = res[f"l{lat}"]; lines.append(f"| (d) {lat} ms row | {x['fills']} | {x['pnl']:+.2f} | {x['lo']:+.2f} to {x['hi']:+.2f} | {100 * x['pos']:.0f}% | {x['per_fill']:+.4f} |")
        lines.append("")
print("\n".join(lines))
json.dump(out, open(f"{DATA}/m2_tables.json", "w"), indent=1)

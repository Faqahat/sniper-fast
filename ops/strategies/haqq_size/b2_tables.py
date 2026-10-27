#!/usr/bin/env python3
"""HAQQ_SIZE step B2 (read-only): pre-send tables per sizing scheme from OUT/presend.pkl (haqq_model/m4_presend_tables.py logic):
  ideal     : every chance alone, first in line; P&L at the scheme's size minus the window's realistic mean failed-try fees
  realistic : the donor-landing replay (run-28 live tries), mean over draws
  calibrated: same, run-28 calibration (wins x 0.81, losses x 1.05)
Base and 20%-fewer-followers stress. Paired differences vs FLAT: the same windows and the same draw (common random numbers), 5-95%
of 4000 bootstrap resamples of the windows. Also the realized mean size per realistic fill. Out: OUT/presend_tables.json"""
import pickle, json
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_size"
Z = pickle.load(open(f"{OUT}/presend.pkl", "rb"))
W = {tuple(x["key"]): x for x in Z["wins"]}
rng = np.random.default_rng(11); NB = 4000
HOURS = 23.75


def mats(scheme, stress, keys):
    R = sorted(Z["real"][(scheme, stress)], key=lambda t: t[0]); nd = len(R)
    net = np.zeros((len(keys), nd)); pnl = np.zeros_like(net); fee = np.zeros_like(net); arm = np.zeros_like(net); fil = np.zeros_like(net)
    for j, (seed, out) in enumerate(R):
        for i, k in enumerate(keys):
            v = out.get(k)
            if v is None: continue
            arm[i, j], fil[i, j], net[i, j], pnl[i, j], fee[i, j] = v[0], v[1], v[2] / 1e9, v[3] / 1e9, v[4] / 1e9
    cal = np.where(pnl > 0, pnl * 0.81, pnl * 1.05) * fil - fee
    return dict(net=net, pnl=pnl, fee=fee, arm=arm, fil=fil, cal=cal)


if __name__ == "__main__":
    IDE = Z["ideal"]
    keys = [k for k in W if k in IDE[("FLAT", False)]]
    n = len(keys)
    schemes = sorted({s for s, _ in Z["real"]}, key=lambda s: ["FLAT", "HAQQ", "SCORE", "HAQQ_FILL"].index(s))
    res = {}
    M = {}
    for st in (False, True):
        for s in schemes: M[(s, st)] = mats(s, st, keys)
    fee_w = None
    for st in (False, True):
        F = M[("FLAT", st)]
        fw = np.where(F["arm"].sum(1) > 0, F["fee"].sum(1) / np.maximum(F["arm"].sum(1), 1), np.nan); fw = np.where(np.isnan(fw), np.nanmean(fw), fw)
        ideal = {s: np.array([IDE[(s, st)][k]["pnl"] if IDE[(s, st)][k]["chance"] else 0.0 for k in keys]) - fw for s in schemes}
        for s in schemes:
            m = M[(s, st)]; f0 = M[("FLAT", st)]
            sz = np.array([Z["sizes"][s][k] for k in keys])
            r = dict(mean_size_fill=float((m["fil"] * sz[:, None]).sum() / m["fil"].sum()))
            ix_all = [rng.integers(0, n, n) for _ in range(NB)]; jd_all = [rng.integers(0, m["net"].shape[1], n) for _ in range(NB)]
            for lab, a, a0 in (("ideal", ideal[s], ideal["FLAT"]), ("realistic", m["net"], f0["net"]), ("calibrated", m["cal"], f0["cal"])):
                if a.ndim == 1:
                    tot = a.sum(); bs = [a[ix].sum() for ix in ix_all]; bd = [(a[ix] - a0[ix]).sum() for ix in ix_all]; dif = (a - a0).sum()
                else:
                    tot = a.sum(0).mean(); dif = (a - a0).sum(0).mean()
                    bs = [a[ix, jd].sum() for ix, jd in zip(ix_all, jd_all)]; bd = [(a[ix, jd] - a0[ix, jd]).sum() for ix, jd in zip(ix_all, jd_all)]
                r[lab] = dict(pnl=float(tot), lo=float(np.percentile(bs, 5)), hi=float(np.percentile(bs, 95)), per_h=float(tot / HOURS),
                              diff=float(dif), dlo=float(np.percentile(bd, 5)), dhi=float(np.percentile(bd, 95)), dpos=float(np.mean(np.array(bd) > 0)))
            r["fills"] = float(m["fil"].sum(0).mean())
            res[f"{s}|{'stress' if st else 'base'}"] = r
    for k, r in res.items():
        print(f"{k:16s} mean size/fill {r['mean_size_fill']:.3f} fills {r['fills']:.0f} | " + " | ".join(
            f"{lab} {r[lab]['pnl']:+.2f} [{r[lab]['lo']:+.2f},{r[lab]['hi']:+.2f}] ({r[lab]['per_h']:+.3f}/h) d {r[lab]['diff']:+.2f} [{r[lab]['dlo']:+.2f},{r[lab]['dhi']:+.2f}]"
            for lab in ("ideal", "realistic", "calibrated")))
    json.dump(res, open(f"{OUT}/presend_tables.json", "w"), indent=1)

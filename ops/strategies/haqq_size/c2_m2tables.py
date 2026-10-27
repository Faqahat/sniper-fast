#!/usr/bin/env python3
"""HAQQ_SIZE step C2 (read-only): M2 (regular dip buys, AMS main) per sizing scheme on the held-out 24 h.
Each row's P&L at the scheme's size = linear interpolation between the built sizes (0.25 .. 1.50; dd1_build replays pump's exact
math at each size with the followers our buy prices out dropped). The engine's tried rows do not depend on size (checked).
Schemes (mean size over the 35 ms fills = 0.55, as live; clip 0.10..1.50):
  FLAT 0.55; HAQQ: his depth-2 rule on the curve SOL after the dump (<= 30.52 -> 0.936, <= 31.06 -> 0.606, else 0.350);
  SCORE: haqq_model score terciles (cutoffs from the pre-send chances, b1_presend.py) -> 0.30 / 0.50 / 0.70.
Rows: ideal = 35 ms row, realistic = 50 ms row, calibrated = 75 ms row (haqq_model's convention). The 20%-fewer-followers stress
is NOT modeled for M2 (dd1_build has no follower cut); it is reported for pre-send only.
Paired bootstrap over rows (4000). Out: OUT/m2_tables.json"""
import pickle, json, glob
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_size"
rng = np.random.default_rng(12); NB = 4000; HOURS = 23.75
R = {}
for f in glob.glob(f"{OUT}/m2/rows_s*.pkl"):
    z = pickle.load(open(f, "rb")); R[z["size"]] = z
SZ = sorted(R)
FE = R[0.55]["feats"]
PS = pickle.load(open(f"{OUT}/presend.pkl", "rb")); T1, T2 = PS["terc"]


def rule(c): return 0.936 if c <= 30.52 else 0.606 if c <= 31.06 else 0.350


def interp(lat, r, s):
    """P&L of row r at size s (linear between grid sizes)"""
    ps = np.array([R[g]["_p"][lat][r] for g in SZ])
    return float(np.interp(s, SZ, ps))


if __name__ == "__main__":
    for g in SZ:
        R[g]["_p"] = {lat: {r: p for r, p, f in R[g][lat]} for lat in (35, 50, 75)}
        R[g]["_f"] = {lat: [(r, f) for r, p, f in R[g][lat]] for lat in (35, 50, 75)}
    for lat in (35, 50, 75):
        same = all(R[g]["_f"][lat] == R[0.55]["_f"][lat] for g in SZ)
        print(f"{lat} ms: tried rows identical across sizes {same}; " + ", ".join(f"{g}:{sum(p for r, p, f in R[g][lat]):+.2f}" for g in SZ))
    rows35 = [(r, f) for r, f in R[0.55]["_f"][35]]
    fill35 = [r for r, f in rows35 if f]
    raw = {"FLAT": lambda r: 0.55, "HAQQ": lambda r: rule(FE[r]["curve"]),
           "SCORE": lambda r: 0.50 if FE[r]["score"] != FE[r]["score"] else (0.30 if FE[r]["score"] < T1 else 0.50 if FE[r]["score"] < T2 else 0.70)}
    size = {}
    for nm, f in raw.items():
        rr = sorted(FE)
        x = np.array([f(r) for r in fill35]); k = 0.55 / x.mean()
        for _ in range(5): k = k * 0.55 / np.clip(x * k, 0.10, 1.50).mean()
        size[nm] = {r: float(np.clip(f(r) * k, 0.10, 1.50)) for r in rr}
        print(f"{nm}: scale {k:.3f}, 35 ms fill sizes mean {np.mean([size[nm][r] for r in fill35]):.3f}; distinct "
              f"{sorted(set(round(v, 2) for v in size[nm].values()))}; n at >= 0.8: {sum(size[nm][r] >= 0.8 for r in fill35)}")
    res = {}
    for lat, lab in ((35, "ideal"), (50, "realistic"), (75, "calibrated")):
        rows = R[0.55]["_f"][lat]
        base = np.array([interp(lat, r, 0.55) if f else R[0.55]["_p"][lat][r] for r, f in rows])
        for nm in raw:
            v = np.array([interp(lat, r, size[nm][r]) if f else R[0.55]["_p"][lat][r] for r, f in rows])
            n = len(v); ixs = [rng.integers(0, n, n) for _ in range(NB)]
            bs = [v[ix].sum() for ix in ixs]; bd = [(v[ix] - base[ix]).sum() for ix in ixs]
            fl = np.array([f for r, f in rows], bool)
            ms = float(np.mean([size[nm][r] for r, f in rows if f]))
            res.setdefault(nm, {})[lab] = dict(pnl=float(v.sum()), lo=float(np.percentile(bs, 5)), hi=float(np.percentile(bs, 95)), per_h=float(v.sum() / HOURS),
                                               diff=float((v - base).sum()), dlo=float(np.percentile(bd, 5)), dhi=float(np.percentile(bd, 95)),
                                               fills=int(fl.sum()), mean_size_fill=ms)
            # split: the rows haqq's rule sizes up vs the rest (where does the difference come from)
            big = np.array([rule(FE[r]["curve"]) > 0.5 for r, f in rows])
            res[nm][lab]["big_rows"] = dict(n=int((big & fl).sum()), pnl_flat=float(base[big].sum()), pnl=float(v[big].sum()),
                                            per_fill_flat=float(base[big & fl].mean()) if (big & fl).any() else 0.0)
    for nm, r in res.items():
        print(f"{nm:6s} " + " | ".join(f"{lab} {x['pnl']:+.2f} [{x['lo']:+.2f},{x['hi']:+.2f}] ({x['per_h']:+.3f}/h, fills {x['fills']}, size/fill {x['mean_size_fill']:.2f}) "
                                       f"d {x['diff']:+.2f} [{x['dlo']:+.2f},{x['dhi']:+.2f}]" for lab, x in r.items()))
    print("dead-curve rows (curve <= 31.06) at flat 0.55:", {lab: res["FLAT"][lab]["big_rows"] for lab in res["FLAT"]})
    json.dump(dict(res=res, sizes={nm: {str(k): v for k, v in s.items()} for nm, s in size.items()}), open(f"{OUT}/m2_tables.json", "w"), indent=1)

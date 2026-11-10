#!/usr/bin/env python3
"""NEWSTRAT step 5: scans on the per-buy event files (n4_events.py).
LEADFOL: wallets (and routes) whose buys we copy at +D and sell after k slots (front-run their followers).
  Leaders picked on FIT days only (10-28/29/30): n >= NMIN on every fit day and mean >= 0 on every fit day and pooled
  mean >= THR mSOL at D=70. Chosen/check on 10-31 (CHOOSE). One position per mint (a trigger inside our open hold is skipped).
RETWAVE: react to a buy when the last 10 slots carry >= RB retail-like buys (buyer with < 30 prior trades in the run) and
  >= RS SOL of them; grid; cells must be > 0 on all 3 fit days; then 10-31.
usage: n5_scan.py   (prints tables; writes OUT/n5.json)"""
import json
import numpy as np
import nlib as L

FIT = L.RUNS[:3]; CH = L.RUNS[3]
KS = [2, 5, 10, 25, 150]

def ev(run):
    z = np.load(f"{L.OUT}/ev_{run}.npz")
    d = {k: z[k] for k in z.files}
    d["hours"] = float(z["hours"][0])
    return d

def one_pos(m, cc, k_slots, D):
    """mask: keep an event only if no kept event on the same mint is still open (entry+D .. +k slots)"""
    o = np.lexsort((cc, m)); keep = np.zeros(len(m), bool)
    mm = m[o].tolist(); cl = cc[o].tolist(); kl = [False] * len(mm)
    lm, lend, h = -1, -1.0, D + k_slots * L.SMS
    for j in range(len(mm)):
        if mm[j] != lm: lm, lend = mm[j], -1.0
        if cl[j] + D >= lend:
            kl[j] = True; lend = cl[j] + h
    keep[o] = kl
    return keep

def day_stats(v, hrs):
    s = L.stats(v); s["per_day"] = round(s["net"] / hrs * 24, 2); return s

if __name__ == "__main__":
    E = {r: ev(r) for r in FIT + [CH]}
    res = {}
    # ---------- LEADFOL by wallet ----------
    print("=== LEADFOL (wallet leaders), D=70")
    for k in KS:
        key = f"d70k{k}"
        per = {}
        for r in FIT:
            d = E[r]; names = d["users"][d["u"]]
            uu, inv = np.unique(names, return_inverse=True)
            n = np.bincount(inv); s = np.bincount(inv, weights=d[key].astype(np.float64))
            per[r] = {u: (n[j], s[j]) for j, u in enumerate(uu)}
        for NMIN in (10, 30):
            for THR in (0.0, 5.0, 10.0):
                common = set.intersection(*[set(u for u, (n, s) in per[r].items() if n >= NMIN and s / n >= 0) for r in FIT])
                lead = set(u for u in common if sum(per[r][u][1] for r in FIT) / sum(per[r][u][0] for r in FIT) >= THR * 1e6)
                row = {"k": k, "NMIN": NMIN, "THR": THR, "leaders": len(lead)}
                for r in FIT + [CH]:
                    d = E[r]; names = d["users"][d["u"]]
                    msk = np.isin(names, list(lead)) if lead else np.zeros(len(names), bool)
                    idx = np.nonzero(msk)[0]
                    kp = one_pos(d["m"][idx], d["cc"][idx], k, 70)
                    idx = idx[kp]
                    row[L.DAY[r]] = day_stats(d[key][idx], d["hours"])
                    if k in (5, 25, 150): row[L.DAY[r]]["f20_day"] = round(float(d[f"f20k{k}"][idx].sum()) / 1e9 / d["hours"] * 24, 2)
                    row[L.DAY[r]]["D0_day"] = round(float(d[f"d0k{k}"][idx].sum()) / 1e9 / d["hours"] * 24, 2)
                    row[L.DAY[r]]["D90_day"] = round(float(d[f"d90k{k}"][idx].sum()) / 1e9 / d["hours"] * 24, 2)
                res.setdefault("leadfol", []).append(row)
                print(f"k{k} NMIN{NMIN} THR{THR} leaders {len(lead)} | " + " | ".join(
                    f"{L.DAY[r]} {row[L.DAY[r]]['per_day']:+.1f}/d n{row[L.DAY[r]]['n']} {row[L.DAY[r]]['per']:+.1f} wo5 {row[L.DAY[r]]['wo5']:+.2f} D0 {row[L.DAY[r]]['D0_day']:+.1f}" for r in FIT + [CH]))
    # ---------- LEADFOL by route ----------
    print("=== LEADFOL (routes), D=70, k=5 and 25: routes with n >= 200 on every fit day, mean > 0 on every fit day")
    for k in (2, 5, 25):
        key = f"d70k{k}"
        per = {}
        for r in FIT + [CH]:
            d = E[r]; names = d["routes"][d["rt"]]
            uu, inv = np.unique(names, return_inverse=True)
            n = np.bincount(inv); s = np.bincount(inv, weights=d[key].astype(np.float64))
            per[r] = {u: (n[j], s[j]) for j, u in enumerate(uu)}
        common = set.intersection(*[set(u for u, (n, s) in per[r].items() if n >= 200) for r in FIT])
        rows = []
        for u in common:
            ms = [per[r][u][1] / per[r][u][0] / 1e6 for r in FIT]
            c = per[CH].get(u, (0, 0.0))
            rows.append((min(ms), u, ms, c[0], (c[1] / c[0] / 1e6) if c[0] else 0.0))
        rows.sort(reverse=True)
        for mn, u, ms, cn, cm in rows[:8]:
            print(f"k{k} route [{u[:60]}] fit mSOL/trip {['%+.1f' % x for x in ms]} | 10-31 n{cn} {cm:+.1f}")
    # ---------- RETWAVE ----------
    print("=== RETWAVE grid, D=70 (cells > 0 on all fit days)")
    grid = []
    for rb in (3, 5, 8, 12, 20):
        for rs in (0.5, 1, 2, 4, 8):
            for ag in ("any", "old"):
                for vsr in ("all", "lt60", "60_85"):
                    for k in (5, 25, 150):
                        cell = {"rb": rb, "rs": rs, "age": ag, "vs": vsr, "k": k}
                        ok = True
                        for r in FIT + [CH]:
                            d = E[r]
                            m = (d["rb10"] >= rb) & (d["rs10"] >= rs)
                            if ag == "old": m &= d["age"] >= 1500
                            if vsr == "lt60": m &= d["vs"] < 60
                            elif vsr == "60_85": m &= (d["vs"] >= 60) & (d["vs"] < 85)
                            idx = np.nonzero(m)[0]
                            kp = one_pos(d["m"][idx], d["cc"][idx], k, 70); idx = idx[kp]
                            st = day_stats(d[f"d70k{k}"][idx], d["hours"])
                            st["f20_day"] = round(float(d[f"f20k{k}"][idx].sum()) / 1e9 / d["hours"] * 24, 2)
                            st["D0_day"] = round(float(d[f"d0k{k}"][idx].sum()) / 1e9 / d["hours"] * 24, 2)
                            cell[L.DAY[r]] = st
                            if r in FIT and st["net"] <= 0: ok = False
                        cell["fit_ok"] = ok
                        grid.append(cell)
    res["retwave"] = grid
    best = sorted(grid, key=lambda c: sum(c[L.DAY[r]]["per_day"] for r in FIT), reverse=True)
    print("fit-positive cells:", sum(c["fit_ok"] for c in grid), "of", len(grid))
    for c in best[:12]:
        print({k: c[k] for k in ("rb", "rs", "age", "vs", "k", "fit_ok")}, " | ".join(
            f"{L.DAY[r]} {c[L.DAY[r]]['per_day']:+.1f}/d n{c[L.DAY[r]]['n']} {c[L.DAY[r]]['per']:+.1f} D0 {c[L.DAY[r]]['D0_day']:+.1f}" for r in FIT + [CH]))
    json.dump(res, open(f"{L.OUT}/n5.json", "w"))

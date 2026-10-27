#!/usr/bin/env python3
# Full evaluation of one detector vs the baseline (IMIT1 top4 = live): every day, 35 / 50 / 75 ms, both live exits, FRA-only and
# FRA+AMS, per-hour P&L, hour-block bootstrap CI of (new - baseline), P&L without the best 1% of trades, extra fixed-cost stress.
# usage: python3 dd8_eval.py <pred name> <threshold> [exit name]
import sys, json
import numpy as np
import dd_lib as L
DAYS = ("R2", "R3", "R1", "R4")
def preds(name):
    P = np.load(f"{L.OUT}/pred_{name}.npy"); out = {}; o = 0
    for day in DAYS:
        n = len(L.load(day)["k"]); out[day] = P[o:o + n]; o += n
    return out
def hourly(d, o):
    h = {}
    for r, sv, p, fl in o["rows"]:
        hb = int(d["t"][r] // 3600); h[hb] = h.get(hb, 0.0) + p
    return h
def boot(hn, hb, n=4000, seed=0):
    ks = sorted(set(hn) | set(hb)); diff = np.array([hn.get(k, 0.0) - hb.get(k, 0.0) for k in ks])
    rng = np.random.default_rng(seed); s = diff[rng.integers(0, len(diff), (n, len(diff)))].sum(1)
    return float(diff.sum()), float(np.percentile(s, 5)), float(np.percentile(s, 95)), float((s <= 0).mean())
if __name__ == "__main__":
    name, thr = sys.argv[1], float(sys.argv[2]); exn = sys.argv[3] if len(sys.argv) > 3 else "c6_tpnone_sl10"
    P = preds(name); cut = np.quantile(L.load("R2")["t"], 0.70)
    out = {}
    for day in DAYS:
        d = L.load(day); win = (d["t"] >= cut) if day == "R2" else np.ones(len(d["t"]), bool); h = L.hours(d) * (0.3 if day == "R2" else 1)
        sel = (P[day] >= thr) & win; base = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]) & win
        print(f"\n=== {day}{' (R2-val = last 30%)' if day == 'R2' else ''} {h:.1f} h")
        for latx, lat in enumerate((35, 50, 75)):
            for en in (exn, "c19_tpnone_sl20") if exn != "c19_tpnone_sl20" else (exn,):
                e = L.EXI[en]
                for sv in (("f",), ("f", "a")):
                    o = L.sim(d, sel, latx, e, servers=sv, detail=True); b = L.sim(d, base, latx, e, servers=sv, detail=True)
                    pn = np.sort([x[2] for x in o["rows"]]); wo = pn[:-max(1, len(pn) // 100)].sum() if len(pn) else 0.0
                    tot, lo, hi, pneg = boot(hourly(d, o), hourly(d, b))
                    tag = "FRA    " if sv == ("f",) else "FRA+AMS"
                    print(f"  {lat}ms {en:16s} {tag} NEW {L.fmt(o, h)} wo_top1% {wo:+6.2f} | BASE {o and L.fmt(b, h)} | diff {tot:+6.2f} [90% CI {lo:+.2f}..{hi:+.2f}] P(<=0) {pneg:.3f}")
                    out[f"{day}|{lat}|{en}|{tag.strip()}"] = dict(new=[o["pnl"], o["fill"], o["att"], o["per_fill"], o["winr"], wo], base=[b["pnl"], b["fill"], b["att"], b["per_fill"], b["winr"]],
                                                                   diff=[tot, lo, hi, pneg])
        # fixed-cost stress (35 ms, FRA+AMS): +0.002 and +0.004 SOL per fill
        for extra in (0.002, 0.004):
            o = L.sim(d, sel, 0, L.EXI[exn], fix=L.FIX + extra); b = L.sim(d, base, 0, L.EXI[exn], fix=L.FIX + extra)
            print(f"  cost +{extra:.3f}/fill 35ms: NEW {o['pnl']:+.2f}  BASE {b['pnl']:+.2f}")
        # per hour PKT (35 ms, FRA+AMS)
        o = L.sim(d, sel, 0, L.EXI[exn], detail=True); b = L.sim(d, base, 0, L.EXI[exn], detail=True)
        hn = hourly(d, o); hb = hourly(d, b)
        print("  per hour PKT (new / base):", " ".join(f"{(k * 3600 // 3600 + 5) % 24:02d}h {hn.get(k, 0):+.2f}/{hb.get(k, 0):+.2f}" for k in sorted(set(hn) | set(hb))))
    json.dump(out, open(f"{L.OUT}/dd8_{name}_{thr:+.4f}_{exn}.json", "w"))

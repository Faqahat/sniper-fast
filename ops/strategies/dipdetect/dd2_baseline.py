#!/usr/bin/env python3
# Baseline (live IMIT1 setup) on the dipdetect replay + cross-check of the replay against the imit2 rows (sel/imit2_build.py).
import sys, gzip, json
import numpy as np
import dd_lib as L
if __name__ == "__main__":
    for day in ("R1", "R2", "R3", "R4"):
        d = L.load(day); h = L.hours(d); f1 = d["f1"]; sc = np.isfinite(f1)
        print(f"\n=== {day} window {L.WIN[day]} ({h:.1f} h): rows {len(f1)}, env(mine) {d['env'].sum()}, IMIT1-scored {sc.sum()}, "
              f"scored&~env {(sc & ~d['env']).sum()}, env&~scored {(d['env'] & ~sc).sum()}")
        for tier in ("top2", "top4", "top8"):
            sel = sc & (f1 >= L.THR[tier])
            for lat in (0, 1):
                for exn, ex in (("1.3s/SL10", L.E_13), ("4s/SL20", L.E_4S)):
                    fra = L.sim(d, sel, lat, ex, servers=("f",)); both = L.sim(d, sel, lat, ex)
                    print(f"  {tier} {(35, 50)[lat]}ms {exn:10s} FRA: {L.fmt(fra, h)} | FRA+AMS: {L.fmt(both, h)}")
    # replay cross-check vs imit2 rows (R3 r3 window): same dumps, P&L at 35 ms, exit no TP / SL -10% / 1.3 s
    d = L.load("R3", window=False); key = {}
    meta = json.load(open("/home/moiz/sniper-data/strategies/patterns/day_R3_meta.json"))["meta"]
    for i in range(len(d["k"])):
        if np.isfinite(d["f1"][i]): key[(meta[d["tok"][i]]["m"], int(d["s"][i]), round(float(d["F"][i, L.FNI["sol"]]), 3))] = i
    a = []; b = []; fa = []; fb = []
    for l in gzip.open("/home/moiz/sniper/ops/overnight/sel/imit2_rows_r3.jsonl.gz", "rt"):
        o = json.loads(l); i = key.get((o["m"], o["s"], o["sell"]))
        if i is None or o["ours"].get("35") is None: continue
        r = o["ours"]["35"]; mine_ok = d["st"][i, 0] == 0; theirs_ok = r["ratio"] <= 1.05
        fa.append(theirs_ok); fb.append(mine_ok)
        if mine_ok and theirs_ok: a.append(r["tpnone_sl10_1.3s"] + 0.0016); b.append(float(d["pnl"][i, 0, L.E_13]))
    a = np.array(a); b = np.array(b); fa = np.array(fa); fb = np.array(fb)
    print(f"\ncross-check R3 night (imit2 vs dipdetect replay), {len(fa)} dumps: guard pass {fa.mean():.3f} vs {fb.mean():.3f}, agree {(fa == fb).mean():.3f}; "
          f"both filled {len(a)}: mean P&L {a.mean():+.4f} vs {b.mean():+.4f}, corr {np.corrcoef(a, b)[0, 1]:.3f}, |diff|<0.002 {(np.abs(a - b) < 0.002).mean():.3f}")

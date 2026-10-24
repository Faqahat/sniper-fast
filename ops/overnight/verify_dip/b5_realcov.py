#!/usr/bin/env python3
"""verify_dip / b5_realcov: are the real decoded follower limits (slip_args.jsonl) biased by WHERE they were fetched?
They were fetched for followers of an earlier model's picks (dip/sel_x_35_8_*.json, score >= thr5). For the CV picks:
coverage (share of window follower buys with a real limit), drop rates real vs imputed on the SAME followers, and the
picks' PnL with real-where-available vs imputed-only.
usage: python3 -I -B b5_realcov.py <cv json> <LAT>"""
import sys, os, json, gzip, zlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import b5_replay as R
def work(arg):
    (tag, b), items, Lm = arg
    data = json.load(gzip.open(os.path.join(R.DIRS[tag], f"b{b:03d}.json.gz"), "rt")); out = {}
    by = collections.defaultdict(list)
    for m, age in items: by[m].append(age)
    for m, ages in by.items():
        c = R.G["L"][m]; tr = R.tape(data[m]["t"]); S = c["slot"]; want = set(ages); sim = R.Sim(tr, R.G["SS_mine"])
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < 1e9: continue
            a = round((t["s"] - S) * R.SMS / 1000, 2)
            if a not in want: continue
            want.discard(a)
            a0 = sim.arr(t); ke = k + 1
            while ke < len(tr) and sim.arr(tr[ke]) < a0 + Lm: ke += 1
            s_in = max(tr[ke - 1]["s"], int((a0 + Lm) // R.SMS)); E = s_in + R.H
            fol = [x for x in tr[ke:] if x["buy"] and not x["syn"] and (x["s"] < E or (x["s"] == E and sim.pos(x) < R.SL))]
            # drop decisions for each follower on the curve right after our buy (first-order: our buy only)
            V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]; fr = R.fbps(t); X = int(R.B * 1e9 / (1 + fr)); q = T * X // (V + X)
            n_real = 0; dr_real = 0; dr_imp_same = 0; sol_real = 0
            for x in fol:
                lim = R.G["REAL"].get(x["sig"])
                if lim is None: continue
                n_real += 1; sol_real += x["sol"]
                # on the real curve before x, shifted by our buy: approximate with the real pre-state of x plus our X/q
                pre = (x["vsol"] - x["sol"], x["vtok"] + x["tok"]); Vx, Tx = pre[0] + X, pre[1] - q
                d = Tx * x["sol"] // (Vx + x["sol"])
                if lim[0] == "sol": dr_real += d < lim[2]
                else:
                    cst = Vx * lim[1] // max(1, Tx - lim[1]) + 1; dr_real += (lim[1] >= Tx) or cst * (1 + fr) > lim[2]
                dr_imp_same += d < x["tok"] / (1 + R.slack(x["sig"]))
            r_with = sim.run([(k, a)], Lm, "c", False)[a][0]
            saved = R.G["REAL"]; R.G["REAL"] = {}
            r_imp = sim.run([(k, a)], Lm, "c", False)[a][0]
            R.G["REAL"] = saved
            out[f"{m}|{a}"] = dict(nf=len(fol), n_real=n_real, dr_real=int(dr_real), dr_imp=int(dr_imp_same), sol_real=sol_real, pnl_real=r_with - 0.0016, pnl_imp=r_imp - 0.0016)
    return out
if __name__ == "__main__":
    cvf, LAT = sys.argv[1], int(sys.argv[2])
    sel = json.load(open(cvf))[str(LAT)]["sel"]
    R.init()
    old = set()
    for fn in ("sel_x_35_8_R1toR2.json", "sel_x_35_8_R2toR1.json"):
        for r in json.load(open(os.path.join(HERE, "..", "dip", fn))):
            if r["score"] >= r["thr5"]: old.add((r["m"], r["age"]))
    by = collections.defaultdict(list)
    for s in sel: by[(R.G["L"][s["m"]]["run"], zlib.crc32(s["m"].encode()) % 256)].append((s["m"], s["age"]))
    res = {}
    with Pool(8, initializer=R.init) as p:
        for o in p.imap_unordered(work, [(k, v, LAT) for k, v in sorted(by.items())]): res.update(o)
    rows = [(res[f"{s['m']}|{s['age']}"], (s["m"], s["age"]) in old) for s in sel if f"{s['m']}|{s['age']}" in res]
    nf = sum(r["nf"] for r, _ in rows); nr = sum(r["n_real"] for r, _ in rows)
    print(f"{os.path.basename(cvf)} L{LAT}: picks {len(rows)}; window follower buys {nf}, with a real decoded limit {nr} ({nr / max(1, nf):.0%})")
    print(f"  on the followers that have both: dropped by the REAL limit {sum(r['dr_real'] for r, _ in rows)}, by the IMPUTED rule {sum(r['dr_imp'] for r, _ in rows)}")
    print(f"  picks' PnL: real where available {sum(r['pnl_real'] for r, _ in rows):+.2f} | imputed only {sum(r['pnl_imp'] for r, _ in rows):+.2f}")
    for flag in (True, False):
        v = [r for r, o in rows if o == flag]
        if v:
            cov = sum(r["n_real"] for r in v) / max(1, sum(r["nf"] for r in v))
            print(f"  picks {'IN' if flag else 'NOT in'} the earlier selection that limits were fetched for: {len(v)}; coverage {cov:.0%}; "
                  f"PnL real {sum(r['pnl_real'] for r in v):+.2f} vs imputed-only {sum(r['pnl_imp'] for r in v):+.2f}")

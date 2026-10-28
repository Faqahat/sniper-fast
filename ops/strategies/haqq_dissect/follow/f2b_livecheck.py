#!/usr/bin/env python3
"""FOLLOW step 2b (read-only): does the fill model (f2: crossing = post price <= 0.88 x the 50-ms reference; k from our live fills by
N_w bucket; fill iff the price after k trades is still under the limit) reproduce the LIVE pre-send fill rate?
Live windows = every pre-send LIVE arm of AMS r9-r33 / FRA r1-r26 (gap/g2_engine.pkl: mint, whale, trigger slot, end slot, filled).
Per window: crossings on the tape (our rows removed) in slots [trigger, end]; model P(fill) = 1 - prod over crossings of P(no fill).
MEASURED live fill vs INFERRED model fill, by whether the window saw a crossing. Out: f2b.txt"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import dv8lib as L
from f2_cross import landing_model, bk
OUT = "/home/moiz/sniper-data/haqq_dissect/follow"


def main():
    R = np.load(f"{OUT}/tape.npy", mmap_mode="r"); X = np.load(f"{OUT}/rowx.npz")
    px = X["px"]; ref = X["ref"]
    MI = pickle.load(open(f"{OUT}/mints.pkl", "rb"))
    st = {int(m): int(a) for m, a in zip(MI["um"], MI["st"])}; en = {int(m): int(b) for m, b in zip(MI["um"], MI["en"])}
    C = np.load(f"{OUT}/cross.npz"); cr = C["row"]; nw = C["nw"]
    crm = np.asarray(R["mint"])[cr].astype(np.int64)
    by = collections.defaultdict(list)
    for i, m in enumerate(crm.tolist()): by[m].append(i)
    q_by = landing_model(R, (st, en))
    ids, idm = L.ids_map()
    Gd = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/gap/g2_engine.pkl", "rb"))
    rng = np.random.default_rng(3)
    rows = []
    for run, Xr in Gd.items():
        if not Xr.get("ps_live"): continue
        for a in Xr["arms"]:
            mint, whale, ts, ens, es, why, filled, t = a[:8]
            m = idm.get(mint)
            if m is None or m not in st: continue
            sl = np.asarray(R["slot"])[[cr[i] for i in by.get(m, [])]] if by.get(m) else np.zeros(0)
            ii = [i for i, s in zip(by.get(m, []), sl.tolist()) if ts <= s <= (es if es else ens)]
            pn = 1.0
            for i in ii:
                x = int(cr[i]); qs = q_by[bk(int(nw[i]))] if bk(int(nw[i])) in q_by else q_by[max(q_by)]
                ks = np.round(qs * nw[i]).astype(int); g = np.minimum(x + ks, en[m] - 1)
                pf = float(np.mean(px[g] <= 0.88 * ref[x]))
                pn *= (1 - pf)
            rows.append((run, len(ii) > 0, bool(filled), 1 - pn, why))
    out = []
    def P(s): print(s); out.append(s)
    r = np.array([(x[1], x[2], x[3]) for x in rows], float)
    P(f"# live pre-send windows {len(rows):,} (runs with pre-send live)")
    for nm, m in (("window saw >= 1 crossing", r[:, 0] == 1), ("no crossing in the window", r[:, 0] == 0)):
        P(f"- {nm}: {int(m.sum()):,} windows, LIVE fill {r[m, 1].mean():.3f} (MEASURED), model fill {r[m, 2].mean():.3f} (INFERRED)")
    by_why = collections.Counter((x[4], x[1], x[2]) for x in rows)
    P("- end reason x crossing x filled: " + ", ".join(f"{k}: {v}" for k, v in sorted(by_why.items(), key=lambda z: -z[1])[:12]))
    open(f"{OUT}/f2b.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

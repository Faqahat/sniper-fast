#!/usr/bin/env python3
"""pos step 10 (read-only): walk-forward of the RE-ARM rule (pre-send style) found in p8/p8c.
Rule (all causal): after a whale dump (single sell >= 6% supply) on a non-mayhem token whose 2-slot result from right after the dump
was >= X (price public at the end of slot dump+2), arm pre-send on that token from slot dump+3 for G slots (2 tries/slot); buy the
next whale dump in the same slot; 2-slot exit; only tokens younger than A s at the arm. Parameters (X, G, A) chosen on day D-1
(net NOW), test on D. Entry = contention-aware pre-send landing (p8c model, measured on our 1,144 live pre-send fills).
Rows: model; calibrated (0.61 x model - 1.17 mSOL per fill, the reactive live fit, used as a haircut -- INFERRED for pre-send);
-10% followers; costs NOW 3.52 mSOL / CHEAP 0.66 per fill + failed tries 5,120 lamports each (2 per armed slot; NOW only, CHEAP
assumes the same). Out: p10.txt"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT, day_name
P = Out(f"{OUT}/p10.txt")
TRY = 5120e-9; TPS = 2


def main():
    Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
    day = ((bt - L.DAY0) // 86400).astype(int)
    C = np.load(f"{OUT}/p8c.npz"); val = C["ps_val"]; fil = C["ps_fill"]; ideal2 = C["ideal2"]
    wh = np.flatnonzero(X[:, 2] >= 6.0)
    o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
    prev = {}; nxt = {}; last = None
    for i in o:
        m = int(M["mint"][i])
        if last is not None and last[0] == m: prev[i] = last[1]; nxt[last[1]] = i
        last = (m, i)
    age = M["age"] * 0.212
    # arm events = whale dumps (usable, not mayhem, valid ideal2); candidate fill = the next whale dump within the window
    ev = [j for j in wh if usable[j] and np.isfinite(ideal2[j])]
    tape = R6.Tape(); rng = np.random.default_rng(21)
    f10cache = {}

    def f10(i):
        if i in f10cache: return f10cache[i]
        # re-simulate with 10% fewer outside buy SOL after entry; same contention draw count (8) as p8c, k from the val/fill share proxy:
        jd = int(M["row"][i]); end = int(M["end"][i]); s0 = int(M["slot"][i]); pre_px = tape.vs[jd - 1] / tape.vt[jd - 1]
        out = []
        for k in rng.choice([0, 0, 0, 0, 0, 0, 1, 1, 2, 3], 8):      # MEASURED live fill k distribution (61% 0, 20% 1, 8% 2, 11% 3+)
            r = min(jd + 1 + int(k), end); px = tape.vs[r - 1] / tape.vt[r - 1]
            if not (px <= 0.88 * pre_px): out.append(0.0); continue
            es = int(tape.sl[r - 1]) if r - 1 > jd else s0
            q = tape.qrow(r, end, es, 2); a = tape.joint([(r, q)], fol=1.0)[0]; b = tape.joint([(r, q)], fol=0.9)[0]
            out.append(b - a)
        f10cache[i] = float(np.mean(out)); return f10cache[i]

    def run(D, Xp, G, A, with_f10=False):
        fills = 0.0; gross = 0.0; tries = 0; n_arm = 0; d10 = 0.0; nf = 0
        for j in ev:
            if day[j] != D or ideal2[j] < Xp or age[j] > A: continue
            n_arm += 1
            i = nxt.get(j)
            gap = (M["slot"][i] - M["slot"][j]) if i is not None else 10 ** 9
            armed = min(G, max(gap - 3, 0))
            if i is not None and 3 <= gap <= G + 2 and usable[i]:
                fills += fil[i]; gross += val[i]; nf += 1
                if with_f10: d10 += f10(i) * fil[i]
                armed = gap - 3
            tries += TPS * armed
        return dict(arms=n_arm, cands=nf, fills=fills, gross=gross, tries=tries, d10=d10)

    def money(r, cost, cal=False):
        g = 0.61 * r["gross"] - 0.00117 * r["fills"] if cal else r["gross"]
        return g - r["fills"] * (0.00352 if cost == "NOW" else 0.00066) - r["tries"] * TRY

    grid = [(x, g, a) for x in (0.02, 0.04, 0.06, 0.1) for g in (10, 25, 50, 100, 400) for a in (30, 120, 600, 1800)]
    P("# RE-ARM pre-send on whale battlegrounds, walk-forward (choose X, G, A on D-1 by calibrated NOW; test D)")
    P("| test day | chosen (X SOL, G slots, A s) | arms | fills | model gross | net NOW | net CHEAP | calibrated NOW | calibrated CHEAP | cal NOW -10% followers | failed-try fees |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    tot = dict(n=0.0, c=0.0, cn=0.0, cc=0.0, f=0.0)
    for D in (1, 2, 3, 4, 5, 6):
        best = max(grid, key=lambda p: money(run(D - 1, *p), "NOW", cal=True))
        r = run(D, *best, with_f10=True)
        row = (money(r, "NOW"), money(r, "CHEAP"), money(r, "NOW", True), money(r, "CHEAP", True))
        f10v = row[2] + 0.61 * r["d10"]
        P(f"| {day_name(D)} | {best} | {r['arms']:,} | {r['fills']:.0f} | {r['gross']:+.2f} | {row[0]:+.2f} | {row[1]:+.2f} | {row[2]:+.2f} | {row[3]:+.2f} | {f10v:+.2f} | {r['tries'] * TRY:.3f} |")
        if 2 <= D <= 5:
            tot["n"] += row[0]; tot["c"] += row[1]; tot["cn"] += row[2]; tot["cc"] += row[3]; tot["f"] += f10v
    P(f"\nSum D2-D5: net NOW {tot['n']:+.2f}, CHEAP {tot['c']:+.2f}; calibrated NOW {tot['cn']:+.2f}, CHEAP {tot['cc']:+.2f}; calibrated NOW -10% followers {tot['f']:+.2f}")
    P("\nFixed rule (X 0.02, G 25, A 120) on every day, for stability:")
    for D in range(7):
        r = run(D, 0.02, 25, 120)
        P(f"- {day_name(D)}: arms {r['arms']:,}, fills {r['fills']:.0f}, model gross {r['gross']:+.2f}, net NOW {money(r, 'NOW'):+.2f}, calibrated NOW {money(r, 'NOW', True):+.2f}, CHEAP {money(r, 'CHEAP', True):+.2f}")
    P.save()


if __name__ == "__main__":
    main()

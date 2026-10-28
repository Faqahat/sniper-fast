#!/usr/bin/env python3
"""BOTS step 13 (read-only): 'BE him on his own picks' tables from b4 (bot replaced) and b4_keep (bot kept as competitor).
SOL/day (mean of D0-D5 full days... per day shown), per bot x entry (his position / our rank landing) x guard (none / +5 %) x exit x followers;
NOW / S2 / CHEAP costs; calibrated with the per-exit calibration of b6 (our live fires, real vs rank) - except the 'his' entry (a real
position, no landing model -> no calibration). Plus the MEASURED shared-dump test: dumps where our live engine fired AND the bot bought.
Out: bots/b13.txt"""
import sys, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/bots")
from b6_wf import calibration, COST
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)


def main():
    Z = pickle.load(open(f"{OUT}/b4_res.pkl", "rb")); Zk = pickle.load(open(f"{OUT}/b4_res_keep.pkl", "rb"))
    PL = [str(p) for p in Z["PL"]]; PLs = PL[1:]
    CAL = calibration(PLs)
    meta = Z["meta"]
    def table(Zr, title):
        res = Zr["res"]
        P(f"\n## {title}")
        P("| bot | entry | guard | exit | lots/day | fill % | curve SOL/day | NOW | S2 | CHEAP | CHEAP fol -10% | CHEAP fol -20% | per day CHEAP (D0..D6) | days > 0 (CHEAP, D0-D5) |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for bot in (247, 248):
            ids = [i for i, m in meta.items() if m["kind"] == "lot" and m["code"] == bot and res.get(i)]
            days = np.array([meta[i]["day"] for i in ids]); nd = 6
            for ent in ("his", "reg"):
                for gi in ("none", "g5"):
                    for a, pol in enumerate(PL):
                        if pol == "('HIS',)" and ent == "reg" and False: pass
                        vals = {}
                        for fi in range(3):
                            pn = []; fl = []
                            for i in ids:
                                es = [e for e in res[i] if (e["m"] == "his" if ent == "his" else e["m"].startswith("reg"))]
                                f = np.array([True if gi == "none" else e["fill5"] for e in es]); v = np.array([e["pn"][fi, a] for e in es])
                                v = np.where(f, np.nan_to_num(v), 0.0); pn.append(v.mean()); fl.append(f.mean())
                            vals[fi] = (np.array(pn), np.array(fl))
                        pn, fl = vals[0]
                        if pol == "('HIS',)": cal = (1.0, 0.0)
                        else:
                            pi = PLs.index(pol); cal = (1.0, 0.0) if ent == "his" else CAL[(gi, pi, 0)][:2]
                        def money(pn, fl, cost, cal):
                            cf, cx = COST[cost]; return cal[0] * pn + cal[1] - fl * cf - (1 - fl) * (cx if gi == "g5" else 0)
                        full = days <= 5
                        row = {c: money(pn, fl, c, cal)[full].sum() / nd for c in COST}
                        c10 = vals[1]; c20 = vals[2]
                        cal1 = cal if (pol == "('HIS',)" or ent == "his") else CAL[(gi, PLs.index(pol), 1)][:2]
                        cal2 = cal if (pol == "('HIS',)" or ent == "his") else CAL[(gi, PLs.index(pol), 2)][:2]
                        f10 = money(c10[0], c10[1], "CHEAP", cal1)[full].sum() / nd; f20 = money(c20[0], c20[1], "CHEAP", cal2)[full].sum() / nd
                        mc = money(pn, fl, "CHEAP", cal); pdv = [mc[days == d].sum() for d in range(7)]
                        P(f"| {bot} | {ent} | {gi} | {pol} | {full.sum() / nd:,.0f} | {100 * fl.mean():.0f} | {pn[full].sum() / nd:+.2f} | {row['NOW']:+.2f} | {row['S2']:+.2f} | {row['CHEAP']:+.2f} | "
                          f"{f10:+.2f} | {f20:+.2f} | " + " ".join(f"{x:+.1f}" for x in pdv) + f" | {sum(x > 0 for x in pdv[:6])}/6 |")
    P("# BE HIM on his own picks: our buy replaces the bot's lot (exact replay; costs per fill NOW 3.52 / S2 1.86 / CHEAP 0.79 mSOL; failed fire 0.53 / 0.36 / 0.04)")
    P("'his' entry = we land exactly where he landed (real position, not modelled; HIS exit reproduces his realized gross: see b4 validation)")
    P("'reg' entry = our regular landing (rank model, 4 draws), calibrated with the per-exit fit on our live fires (b6); HIS exit uncalibrated")
    for bot in (247, 248):
        ids = [i for i, m in meta.items() if m["kind"] == "lot" and m["code"] == bot and Z["res"].get(i)]
        g = np.array([meta[i]["gross"] for i in ids]); s = np.array([Z["res"][i][0]["pn"][0, 0] for i in ids]); n = np.array([meta[i]["net"] for i in ids])
        ok = np.isfinite(s)
        P(f"- validation {bot}: {ok.sum():,} lots; his realized gross {g[ok].sum():+.2f} SOL, replay of his own entry + his own sells {s[ok].sum():+.2f}; within 1 mSOL on {100 * np.mean(np.abs(g[ok] - s[ok]) < 0.001):.0f}% of lots; his net (after his tx costs) {n.sum():+.2f}")
    table(Z, "Bot REPLACED (his lot removed from the tape)")
    table(Zk, "Bot KEPT (his lot stays: he competes for the same dump)")
    open(f"{OUT}/b13.txt", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

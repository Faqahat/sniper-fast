#!/usr/bin/env python3
"""WHALEFLIP step 7: score w5's paired replay. Per variant and period/segment: windows, blocked live fills (the live fill try is not our
fill any more), precision (losers among blocked), DIRECT (= minus the realized P&L of the blocked fills, MEASURED), REPLAY delta
(variant - baseline incl. re-fills and extra failed tries, INFERRED parts), w/o top 5 gains, SOL/day on the covered hours.
Calibration: model exit on the live fill try ("C") vs its real realized P&L.
usage: w7_score.py PERIODS (e.g. DEV,VAL  or  DEV,VAL,HOLD)"""
import sys, json, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W
pers = sys.argv[1].split(",")
R = json.load(open(f"{W.D}/replay.json"))["rows"]
F = W.load(); h, hp, P = W.hours(F)
nall = collections.Counter(f["seg"] for f in F if f["kind"] == "t2")
ncov = collections.Counter(r["seg"] for r in R)
hcov = {s: h[s] * ncov[s] / nall[s] for s in ncov}            # covered hours ~ hours x covered share of the segment's T2 fills
SEGS = [s for s in ["r39", "r40", "r41", "r42a", "r42b", "r43", "r44", "r45", "r46", "r47", "r48"] if any(s in P[p] for p in pers)]
R = [r for r in R if r["period"] in pers]
print("covered T2 fills / all and covered hours:", {s: f"{ncov[s]}/{nall[s]} {hcov.get(s, 0):.1f}h" for s in SEGS})
# calibration
c = [(r["v"]["C"]["fill_pnl"], r["pnl_live"]) for r in R]
for per in pers:
    cc = [(r["v"]["C"]["fill_pnl"], r["pnl_live"]) for r in R if r["period"] == per]
    if cc:
        err = sorted(a - b for a, b in cc)
        print(f"calibration {per}: model exit on the live fill {sum(a for a, _ in cc):+.3f} vs realized {sum(b for _, b in cc):+.3f} (n {len(cc)}; per-fill error median {err[len(err)//2]*1000:+.1f} mSOL, p10 {err[len(err)//10]*1000:+.1f}, p90 {err[len(err)*9//10]*1000:+.1f})")
VARS = [v for v in R[0]["v"] if v not in ("none", "C")]
out = {}
print(f"\n{'variant':7s} {'period':6s} | {'blocked':>7s} {'losers':>6s} {'prec':>5s} {'direct':>7s} | {'refill n':>8s} {'refill':>7s} {'xfee':>7s} | {'REPLAY':>7s} {'w/o top5':>8s} {'SOL/day':>7s} | per segment REPLAY")
for v in VARS:
    for per in pers + ["+".join(pers)]:
        rr = [r for r in R if per == "+".join(pers) or r["period"] == per]
        blk = [r for r in rr if r["v"][v]["src"].get("live", 0) < sum(r["v"][v]["src"].values())]
        frac = {id(r): 1 - r["v"][v]["src"].get("live", 0) / sum(r["v"][v]["src"].values()) for r in rr}
        direct = -sum(r["pnl_live"] * frac[id(r)] for r in blk)
        los = sum(frac[id(r)] for r in blk if r["pnl_live"] < 0); nb = sum(frac[id(r)] for r in blk)
        d = [r["v"][v]["pnl"] - r["v"]["none"]["pnl"] for r in rr]
        refill = sum(r["v"][v]["fill_pnl"] for r in blk if r["v"][v]["src"].get("live", 0) == 0)
        nref = sum(r["v"][v]["filled"] for r in blk if r["v"][v]["src"].get("live", 0) == 0)
        xfee = sum(-(r["v"][v]["fails"] - r["v"]["none"]["fails"]) * 5120 / 1e9 for r in rr)
        hrs = sum(hcov.get(s, 0) for s in SEGS if (per == "+".join(pers) or s in P[per]))
        sd = sorted(d)
        segs = {s: round(sum(r["v"][v]["pnl"] - r["v"]["none"]["pnl"] for r in rr if r["seg"] == s), 3) for s in SEGS if any(r["seg"] == s for r in rr)}
        o = {"blocked": round(nb, 1), "losers": round(los, 1), "precision": round(los / nb, 3) if nb else None, "direct": round(direct, 3), "refill_n": round(nref, 1),
             "refill": round(refill, 3), "xfee": round(xfee, 3), "replay": round(sum(d), 3), "wo_top5": round(sum(sd[:-5]), 3), "sol_day": round(sum(d) / hrs * 24, 3) if hrs else None,
             "hours": round(hrs, 1), "segments": segs, "seg_pos": sum(1 for x in segs.values() if x > 0), "seg_n": len(segs)}
        out[f"{v}|{per}"] = o
        print(f"{v:7s} {per:6s} | {nb:7.1f} {los:6.1f} {o['precision'] or 0:5.2f} {direct:+7.3f} | {nref:8.1f} {refill:+7.3f} {xfee:+7.3f} | {sum(d):+7.3f} {o['wo_top5']:+8.3f} {o['sol_day'] or 0:+7.2f} | " + " ".join(f"{s} {x:+.2f}" for s, x in segs.items()))
json.dump(out, open(f"{W.D}/score_{'_'.join(pers)}.json", "w"), indent=1)

#!/usr/bin/env python3
# Totals from v2_cv.py out-of-fold files: modes none (top Q of all), filter (top Q of all, direct triggers only), thr (top Q among
# direct), routed (top Q of all, routed only); 2% guard (px <= 1.02, else a failed tx at -0.0002); per block; bootstrap over
# launches within blocks; without the best 10 launches. usage: python3 -I v2_oof_analyze.py oof1.jsonl [oof2.jsonl ...]
import sys, json, collections, random
GUARD = 1.02
def load(p):
    R = collections.defaultdict(list)
    for l in open(p):
        r = json.loads(l); R[r["LAT"]].append(r)
    return R
def pick(r, mode):
    if mode == "none": return r["f"] >= r["thr"]
    if mode == "filter": return r["f"] >= r["thr"] and r["d"] == 1
    if mode == "thr": return r["f"] >= r["thr_d"] and r["d"] == 1
    if mode == "routed": return r["f"] >= r["thr"] and r["d"] == 0
def val(r, guard): return (r["pnl"] if r["px"] <= GUARD else -0.0002) if guard else r["pnl"]
def boot(S, guard, n=2000, seed=11):
    rnd = random.Random(seed); byb = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in S: byb[r["block"]][r["m"]] += val(r, guard)
    blocks = {b: list(v.values()) for b, v in byb.items()}; out = []
    for _ in range(n): out.append(sum(sum(rnd.choice(v) for _ in v) for v in blocks.values()))
    out.sort(); return out[int(.025 * n)], out[int(.975 * n)], sum(1 for x in out if x <= 0) / n
def no_top10(S, guard):
    bym = collections.defaultdict(float)
    for r in S: bym[r["m"]] += val(r, guard)
    v = sorted(bym.values(), reverse=True); return sum(v[10:])
if __name__ == "__main__":
    for p in sys.argv[1:]:
        R = load(p); print(f"\n##### {p}")
        for LAT, rows in R.items():
            for mode in ("none", "filter", "thr", "routed"):
                S = [r for r in rows if pick(r, mode)]
                if not S: continue
                tot = sum(r["pnl"] for r in S); g = sum(val(r, True) for r in S)
                pb = collections.defaultdict(float); pbg = collections.defaultdict(float)
                for r in S: pb[r["block"]] += r["pnl"]; pbg[r["block"]] += val(r, True)
                line = f"LAT {LAT:3s} {mode:6s}: n {len(S):5d} total {tot:+7.2f} (mean {tot / len(S):+.4f}) | guard {g:+7.2f} | blocks " + " ".join(f"{pb[b]:+.2f}" for b in sorted(pb))
                if mode in ("filter", "none"):
                    lo, hi, pn = boot(S, False); glo, ghi, gpn = boot(S, True)
                    line += f" | boot95 [{lo:+.1f},{hi:+.1f}] guard [{glo:+.1f},{ghi:+.1f}] | w/o best 10 launches {no_top10(S, False):+.2f} guard {no_top10(S, True):+.2f}"
                    line += " | guard blocks " + " ".join(f"{pbg[b]:+.2f}" for b in sorted(pbg))
                print(line)

#!/usr/bin/env python3
# HkQ7hMjy exit policy as a sell hazard: P(its sell lands at slot s | still holding) by slots held and by the position value
# known D slots earlier (last trade before slot s-D). Uses hk_paths.json from hk_rule_fit.py. Local only.
import json, collections, statistics, sys
R = json.load(open("/home/moiz/sniper/ops/overnight/hkq7/hk_paths.json"))
D = int(sys.argv[1]) if len(sys.argv) > 1 else 1
def v_at(r, s):
    v = 1.0
    for so, val, _, _ in r["path"]:
        if so < s: v = val
        else: break
    return v
def mx_at(r, s):
    m = 1.0
    for so, val, _, _ in r["path"]:
        if so < s: m = max(m, val)
        else: break
    return m
VB = [(0, 0.90, "<0.90"), (0.90, 0.97, "0.90-0.97"), (0.97, 1.0, "0.97-1.00"), (1.0, 1.03, "1.00-1.03"), (1.03, 1.08, "1.03-1.08"), (1.08, 1.2, "1.08-1.20"), (1.2, 99, ">=1.20")]
SB = [(3, 4), (4, 6), (6, 7), (7, 10), (10, 15), (15, 25), (25, 40), (40, 80)]
at = collections.Counter(); sold = collections.Counter()
for r in R:
    for s in range(3, min(r["hold"], 79) + 1):
        v = v_at(r, s - D)
        vb = next(lab for lo, hi, lab in VB if lo <= v < hi)
        sb = next((f"{a}-{b - 1}" for a, b in SB if a <= s < b), None)
        if sb is None: continue
        at[(sb, vb)] += 1
        if s == r["hold"]: sold[(sb, vb)] += 1
print(f"sell hazard per slot (share of still-open positions whose sell lands in that slot), value known {D} slot(s) earlier; n = open position-slots")
print(f"{'slots held':>10} | " + " | ".join(f"{lab:>12}" for _, _, lab in VB))
for a, b in SB:
    sb = f"{a}-{b - 1}"
    print(f"{sb:>10} | " + " | ".join(f"{sold[(sb, lab)] / at[(sb, lab)]:6.0%} n{at[(sb, lab)]:<5d}" if at[(sb, lab)] >= 20 else f"{'-':>12}" for _, _, lab in VB))
# the 6-slot spike: up or down?
six = [r for r in R if r["hold"] == 6]
print(f"\nsold at exactly 6 slots: {len(six)}; share sold up (real >= 1): {sum(1 for r in six if r['real'] >= 1) / len(six):.0%}; value at slot 5: median {statistics.median(v_at(r, 5) for r in six):.3f}")
for lo, hi in ((3, 6), (6, 7), (7, 12), (12, 25), (25, 60), (60, 10 ** 6)):
    g = [r for r in R if lo <= r["hold"] < hi]
    if g: print(f"hold {lo}-{hi - 1 if hi < 10 ** 6 else '+'}: n {len(g)}, sold up {sum(1 for r in g if r['real'] >= 1) / len(g):.0%}, real exit value median {statistics.median(r['real'] for r in g):.3f}, mean {statistics.mean(r['real'] for r in g):.3f}, "
                  f"value at slot 5 median {statistics.median(v_at(r, 5) for r in g):.3f}, max before sell median {statistics.median(mx_at(r, r['hold']) for r in g):.3f}")
tot = sum((r["real"] - 1) * 0.5 for r in R)
print(f"\nall {len(R)} simple trips: sum of (exit value - 1) x 0.5 SOL = {tot:+.2f} SOL (before tips/priority fees)")
# what if it had sold every trip at exactly 6 slots (value at slot 6 known 1 slot earlier)? rough, no price impact of its own sell
alt = sum((v_at(r, 6) - 1) * 0.5 for r in R)
print(f"rough alt: if it had sold every trip at the value of slot 5 (sell lands slot 6): {alt:+.2f} SOL")

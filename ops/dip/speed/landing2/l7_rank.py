#!/usr/bin/env python3
# LANDING2 step 7: rank the time sinks. For each fix scenario, move each affected fire's landing earlier on the block clock and read the
# MEASURED guard state at the new position (guard_at_ms grid, state at or before) -> fills out of 250. SOL/day is INFERRED from the
# corrected replay's "price of speed" curve (RECON.md: our real landing +1.06 SOL/day both servers; 5 / 10 / 20 / 30 / 50 ms faster
# +4.9 / +6.4 / +8.7 / +9.3 / +10.7; first in line +13.2), scaled by the share of fires a fix touches.
import json, sys, io, contextlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
with contextlib.redirect_stdout(io.StringIO()):
    from l4_tables import L, grp, quart, first_react, best_pro, P, pct

GRID = [0, 2, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 75, 100, 150, 212, 300]
V = [(0, 1.06), (5, 4.9), (10, 6.4), (20, 8.7), (30, 9.3), (50, 10.7), (1e9, 10.7)]


def v_of(d):
    for (x0, y0), (x1, y1) in zip(V, V[1:]):
        if x0 <= d <= x1: return y0 + (y1 - y0) * (d - x0) / (x1 - x0)
    return V[-1][1]


def passes(r, d):
    """the guard state just before a landing d ms after the dump (block clock): the last trade strictly before d"""
    st = True
    for ms, ok in r["C"]["gms"]:
        if ms < d: st = ok
        else: break
    return st


def fills(newd):
    return sum(1 for r in L if passes(r, newd(r)))


base_grid = fills(lambda r: r["C"]["our_ms"])
real = sum(r["C"]["our_ok"] for r in L)
print(f"fills: chain {real}/250; guard grid at our real landing {base_grid}/250 (grid rounding check)")
ss_med = lambda g: float(np.median([r["W"]["send_to_seen"] for r in L if grp(r) == g and r["C"]["slot_delta"] == 0 and r["W"]["send_to_seen"] is not None]))
w2s = {g: ss_med(g) for g in ("bam", "harmonic", "jito-own", "jito-relayer", "fd")}
print("same-slot write->seen medians:", {k: round(v, 1) for k, v in w2s.items()})


def shift(pred, delta):
    """land `delta(r)` ms earlier for fires matching pred"""
    return lambda r: r["C"]["our_ms"] - (delta(r) if pred(r) else 0)


scen = []
eng = lambda r: max(0.0, min(r["W"]["exec_wait"] + 0.4, r["W"]["first_write"] - 0.3))
scen.append(("E. Engine: fire on the first shred + logs after the send (saves the exec-feed wait + 0.4 ms)", lambda r: True, eng))
scen.append(("J1. Jito own-TPU send leg as fast as our BAM leg", lambda r: grp(r) == "jito-own", lambda r: w2s["jito-own"] - w2s["bam"]))
scen.append(("J2. Jito relayer leaders as fast as our BAM leg", lambda r: grp(r) == "jito-relayer", lambda r: w2s["jito-relayer"] - w2s["bam"]))
scen.append(("H. Harmonic send leg as fast as our BAM leg", lambda r: grp(r) == "harmonic", lambda r: w2s["harmonic"] - w2s["bam"]))
scen.append(("F1. Pre-confirmation feed on BAM + Harmonic, low (5 ms)", lambda r: grp(r) in ("bam", "harmonic"), lambda r: 5.0))
scen.append(("F2. Pre-confirmation feed on BAM + Harmonic, high (10 ms)", lambda r: grp(r) in ("bam", "harmonic"), lambda r: 10.0))
scen.append(("D. DoubleZero-class shred feed (1.4 ms, all)", lambda r: True, lambda r: 1.4))
scen.append(("A. Send leg 10 ms faster on every client", lambda r: True, lambda r: 10.0))
scen.append(("B. Send leg 20 ms faster on every client", lambda r: True, lambda r: 20.0))
for name, pred, delta in scen:
    f = fills(shift(pred, delta)); n = sum(1 for r in L if pred(r))
    dm = float(np.mean([delta(r) for r in L if pred(r)])) if n else 0
    sol = n / len(L) * (v_of(dm) - V[0][1])
    print(f"| {name} | {n} | {dm:.1f} | {dm * n / len(L):.1f} | {f - base_grid:+d} | {sol:+.1f} |")

# spills: avoidable ones (a reacting rival got into the dump's block) land at the end of the dump's block instead
avoid = lambda r: r["C"]["slot_delta"] > 0 and (lambda x: x is not None and x["ds"] == 0)(first_react(r))
newd = lambda r: (r["C"]["left_ms"] - 1.0) if avoid(r) else r["C"]["our_ms"]
n = sum(1 for r in L if avoid(r)); dm = float(np.mean([r["C"]["our_ms"] - (r["C"]["left_ms"] - 1) for r in L if avoid(r)]))
print(f"| S. Avoidable spills land at the end of the dump's block | {n} | {dm:.1f} | {dm * n / len(L):.1f} | {fills(newd) - base_grid:+d} | {n / len(L) * (v_of(dm) - V[0][1]):+.1f} |")
alls = lambda r: r["C"]["slot_delta"] > 0
newd2 = lambda r: (r["C"]["left_ms"] - 1.0) if alls(r) else r["C"]["our_ms"]
n2 = sum(1 for r in L if alls(r)); dm2 = float(np.mean([r["C"]["our_ms"] - (r["C"]["left_ms"] - 1) for r in L if alls(r)]))
print(f"| S2. ALL spills land at the end of the dump's block | {n2} | {dm2:.1f} | {dm2 * n2 / len(L):.1f} | {fills(newd2) - base_grid:+d} | {n2 / len(L) * (v_of(dm2) - V[0][1]):+.1f} |")
# land like the first reacting rival / the best named pro on each dump
for name, pick in (("first reacting rival", first_react), ("best named pro", best_pro)):
    def nd(r, pick=pick):
        x = pick(r)
        return min(r["C"]["our_ms"], x["ms"] - 0.1) if x else r["C"]["our_ms"]
    gaps = [r["C"]["our_ms"] - nd(r) for r in L]
    print(f"| Land just before the {name} on each dump | {sum(1 for g in gaps if g > 0)} | {np.mean([g for g in gaps if g > 0]):.1f} | {np.mean(gaps):.1f} | "
          f"{fills(nd) - base_grid:+d} | – |")
# combined realistic package
def combo(r):
    d = r["C"]["our_ms"] - eng(r)
    g = grp(r)
    if g == "jito-own": d -= (w2s["jito-own"] - w2s["bam"])
    if g == "jito-relayer": d -= (w2s["jito-relayer"] - w2s["bam"])
    if g == "harmonic": d -= (w2s["harmonic"] - w2s["bam"])
    if avoid(r): d = min(d, r["C"]["left_ms"] - 1.0)
    return d
cm = float(np.mean([r["C"]["our_ms"] - combo(r) for r in L]))
print(f"| PACKAGE: engine + Jito & Harmonic legs like BAM + avoidable spills | 250 | {cm:.1f} | {cm:.1f} | {fills(combo) - base_grid:+d} | {v_of(cm) - V[0][1]:+.1f} |")

# guard pass rate by landing bin (MEASURED curve on these 250 fires, block clock)
print("\nGuard pass rate if every buy landed d ms after the dump (block clock, these 250 fires):")
print("| d (ms) | " + " | ".join(str(d) for d in (0, 5, 10, 20, 30, 35, 40, 50, 60, 75, 100)) + " |")
print("|---|" + "---|" * 11)
print("| pass | " + " | ".join(pct(sum(1 for r in L if passes(r, d)), len(L)) for d in (0, 5, 10, 20, 30, 35, 40, 50, 60, 75, 100)) + " |")
for g in ("bam", "harmonic", "jito-own", "jito-relayer"):
    rows = [r for r in L if grp(r) == g]
    print(f"| {g} | " + " | ".join(pct(sum(1 for r in rows if passes(r, d)), len(rows)) for d in (0, 5, 10, 20, 30, 35, 40, 50, 60, 75, 100)) + " |")

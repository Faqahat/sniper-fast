#!/usr/bin/env python3
# e10: ROBUST choice of a simple "hold while outside buying continues" rule, on TRAIN only.
# Rule BUYING(X, b, kmin, R, cap): at the start of each slot k >= kmin after our buy, HOLD if an outside buy of >= b SOL landed in the
# last X ms (block clock) and the position is up less than R; otherwise SELL. Forced sell at tick cap.
# Criterion (maximin): the WORST improvement over today's exit (c4) across 6 TRAIN cells = {M2, IMIT1} x {09:45-15:00, 15:00-21:00,
# 21:00-01:00} (engine SOL/day, our measured landing). The chosen rule is then reported on TEST once (e05 / e07).
# -> /home/moiz/sniper-data/exits/e10_select.json/.txt
import sys, os, json, time, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E

OUT = f"{E.DATA}/e10_select"
CELLS = [("10-24 09:45", "10-24 15:00"), ("10-24 15:00", "10-24 21:00"), ("10-24 21:00", "10-25 01:00")]


def buying_rule(d, X, b, kmin, R, cap, F=None):
    """hold iff an outside buy >= b SOL in the last X ms before the slot start (X <= 212: the last slot; uses stall_ms when b == 0,
    else the last-slot / last-2-slot buy SOL windows) and r < R"""
    F = d.ft if F is None else F; I = d.TFI; K = d.K
    if b <= 0:
        active = F[:, :, I["stall_ms"]] < X
    else:
        # time of the last buy >= b is not a feature; approximate with windows: X <= 212 -> last slot, else last 2 slots
        active = (F[:, :, I["maxb2"]] >= b) if X > 212 else ((F[:, :, I["bsol1"]] >= b) & (F[:, :, I["stall_ms"]] < X))
    hold = active
    if R is not None: hold = hold & (F[:, :, I["r"]] < R)
    ks = np.arange(1, K + 1)[None, :]
    sell = (~hold & (ks >= kmin)) | (ks >= cap)
    return d.tick_policy(sell.argmax(1) + 1)


if __name__ == "__main__":
    T0 = time.time()
    d = V.Data(); D = d.D
    per = [(E.pk(a), E.pk(b)) for a, b in CELLS]
    def cells(pol):
        val, tdec, knd = pol; pnl = d.pnl(val, 0); out = []
        for w in ("M2", "IMIT1"):
            for p in per:
                e = d.engine(d.picks(w), pnl, tdec, knd, lmode="meas", R=12, period=p); out.append(V.fmt_day(e["pnl"], p))
        return np.array(out)
    base = cells(d.tick_policy(np.full(len(d.s_in), 4)))
    grid = list(itertools.product((100, 150, 192, 250, 300, 424), (0.0, 0.1, 0.3, 0.5), (1, 2, 3), (None, 0.08, 0.15, 0.25), (9, 20, 30)))
    res = {}
    for i, g in enumerate(grid):
        c = cells(buying_rule(d, *g)); res[str(g)] = (c - base).tolist()
        if (i + 1) % 100 == 0: print(f"  {i + 1}/{len(grid)} rules, {time.time() - T0:.0f} s", flush=True)
    order = sorted(grid, key=lambda g: (-min(res[str(g)]), -sum(res[str(g)])))
    lines = []
    def L(s=""): lines.append(s); print(s)
    L("BUYING(X ms, b SOL, kmin, R, cap) chosen on TRAIN by the worst-cell gain over c4 (SOL/day). cells: M2 x 3 periods, IMIT1 x 3 periods")
    L(f"c4 itself in the cells: {np.round(base, 2).tolist()}")
    for g in order[:20]:
        r = res[str(g)]
        L(f"  {str(g):30s} worst {min(r):+.2f} sum {sum(r):+.2f} cells {np.round(r, 2).tolist()}")
    json.dump(dict(res=res, base=base.tolist(), best=[list(g) if not isinstance(g, list) else g for g in order[:20]]), open(f"{OUT}.json", "w"), default=str)
    open(f"{OUT}.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")

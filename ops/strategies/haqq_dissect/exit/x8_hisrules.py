#!/usr/bin/env python3
"""EXIT step 8 (read-only): haqq's exits vs simple causal rules, and selection vs timing (MEASURED on the tape; replays INFERRED).
Lots: his non-DEAD lots (types DIP / ADD / DIP_LATE / OTHER / LAUNCH / MOMO) whose exit (the sell that closed the lot) lies inside
the 300-slot path (paths.npz).
Part A - rule matching on what he SAW (va = the lot's sell value / cost on the real tape after each outside trade):
  a rule fires at the first outside trade j meeting its condition; its earliest sell = max(t_j, start of slot buy+2) (he never
  sells before slot buy+2: 1 of 31,948 lots). hit = his exit lands within 400 ms after that; early = it fired but he sold later;
  miss = it had not fired when he sold. precision = hit / (hit + early); recall = hit / lots.
  Chance level: the same rule with its firing time moved to a random time in the lot's hold (seeded), same scoring.
Part B - P&L of rules applied UNIFORMLY to all his lots, exact replay of the lot alone (vx; his later trades removed), sell
  landing = trigger + his reaction delay (quantiles of his DIP buys' delay after the dump, MEASURED), timers at slot start + same
  delay; grouped by his ACTUAL hold (<2 s / 2-15 s / 15-60 s / >60 s), per day, and at 10% fewer followers (vx9).
Out: haqq_dissect/exit/x8.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
QS = (5, 15, 25, 35, 45, 55, 65, 75, 85, 95)
W = 400.0
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); LOTS = Z["lots"]; POS = Z["pos"]
    A = np.load(f"{X.OUT}/paths.npz")
    off = A["off"]; ex = A["lot_exit"]; DCC = A["dcc"]; BU = A["buy"]; SO = A["sol"]; VA = A["va"]; VX = A["vx"]; VX9 = A["vx9"]
    dmy = np.percentile([L["d_ms"] for L in LOTS if L["t"] == "DIP" and L.get("d_ms") is not None], QS)
    P("# haqq's exits vs causal rules (non-DEAD lots), tape 10-22 03:07 -> 10-28 01:12 PKT")
    P(f"his reaction delay quantiles {QS} (dump -> his DIP buy, chain-clock ms, MEASURED): " + " ".join(f"{x:.0f}" for x in dmy))
    lots = []
    for i, L in enumerate(LOTS):
        if L["t"] == "DEAD" or L["close_cc"] is None: continue
        a, b = off[i], off[i + 1]; n = b - a
        if n == 0: continue
        e = ex[i]; xt = L["close_cc"] - L["cc"]
        inside = 0 < e < n
        lots.append((i, a, b, xt, inside))
    P(f"lots: {len(lots):,}; exit inside the 300-slot path {sum(x[4] for x in lots):,}")
    rng = np.random.default_rng(7)
    # ---------------- Part A
    rules = []
    for x in (0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50): rules.append((f"TP +{x:.0%}", lambda d, x=x: d["va"] >= 1 + x))
    for y in (0.05, 0.10, 0.20, 0.30): rules.append((f"SL -{y:.0%}", lambda d, y=y: d["va"] <= 1 - y))
    for X_ in (0.1, 0.25, 0.5, 1.0, 2.0, 3.0): rules.append((f"follower buy >= {X_}", lambda d, X_=X_: d["bu"] & (d["so"] >= X_)))
    for X_, x in ((0.5, 0.0), (0.5, 0.05), (1.0, 0.05), (1.0, 0.10), (2.0, 0.10)): rules.append((f"follower buy >= {X_} & ret >= +{x:.0%}", lambda d, X_=X_, x=x: d["bu"] & (d["so"] >= X_) & (d["va"] >= 1 + x)))
    for X_ in (0.5, 1.0, 2.0, 3.0): rules.append((f"outside sell >= {X_}", lambda d, X_=X_: ~d["bu"] & (d["so"] >= X_)))
    for a_, z in ((0.05, 0.03), (0.10, 0.05), (0.20, 0.10)): rules.append((f"trail: best >= +{a_:.0%}, give back {z:.0%}", lambda d, a_=a_, z=z: (np.maximum.accumulate(d["va"]) >= 1 + a_) & (d["va"] <= np.maximum.accumulate(d["va"]) - z)))
    res = {nm: collections.Counter() for nm, _ in rules}; resc = {nm: collections.Counter() for nm, _ in rules}
    nin = 0
    for i, a, b, xt, inside in lots:
        if not inside: continue
        nin += 1; L = LOTS[i]
        d = dict(va=VA[a:b].astype(np.float64), bu=BU[a:b], so=SO[a:b].astype(np.float64)); dc = DCC[a:b].astype(np.float64)
        s2 = 2 * X.SMS - (L["cc"] - L["slot"] * X.SMS)
        for nm, f in rules:
            m = f(d) & (dc <= max(xt, 1.0) + 60000)
            j = int(np.argmax(m)) if m.any() else None
            for tag, tj in (("r", dc[j] if j is not None else None), ("c", rng.uniform(0, xt + 2000) if j is not None else None)):
                R = res[nm] if tag == "r" else resc[nm]
                if tj is None or tj >= xt: R["miss"] += 1; continue
                te = max(tj, s2)
                if xt <= te + W: R["hit"] += 1
                else: R["early"] += 1
    P(f"\n## A. Rule matching on {nin:,} lots (window {W:.0f} ms after the rule's earliest sell)")
    P("| rule | fired before his exit | hit | precision % | recall % | chance precision % | chance recall % |"); P("|---|---|---|---|---|---|---|")
    for nm, _ in rules:
        r = res[nm]; c = resc[nm]
        f = r["hit"] + r["early"]; fc = c["hit"] + c["early"]
        P(f"| {nm} | {100 * f / nin:.0f}% | {r['hit']:,} | {100 * r['hit'] / max(f, 1):.1f} | {100 * r['hit'] / nin:.1f} | {100 * c['hit'] / max(fc, 1):.1f} | {100 * c['hit'] / nin:.1f} |")
    # ---------------- Part B: uniform policies on his lots, exact replay
    def pol_val(v, dc, bu, so, s0, N, kind, prm):
        """exit value for one lot under a policy; s0 = ms offset of slot start 0 relative to the buy (negative)"""
        tmin = 2 * X.SMS + s0                              # his minimum hold: slot buy+2
        tN = N * X.SMS + s0
        def at(t): return float(np.mean([v[q] if q >= 0 else 0.975 for q in (np.searchsorted(dc, t + dmy, side="right") - 1)]))
        if kind == "T": return at(tN)
        if kind == "FB": m = bu & (so >= prm)
        elif kind == "TP": m = v >= 1 + prm
        elif kind == "TPSL": m = (v >= 1 + prm[0]) | (v <= 1 - prm[1])
        elif kind == "FBP": m = bu & (so >= prm[0]) & (v >= 1 + prm[1])
        j = int(np.argmax(m)) if m.any() else None
        if j is not None and dc[j] < tN: return at(max(dc[j], tmin))
        return at(tN)
    pols = [("ACT", None, None)] + [("T", n, None) for n in (2, 3, 5, 8, 10, 15, 20, 30, 60)]
    pols += [("FB", n, x) for x in (0.25, 0.5, 1.0, 2.0) for n in (5, 10, 20, 30)]
    pols += [("TP", n, x) for x in (0.05, 0.10, 0.20) for n in (10, 20, 30)]
    pols += [("TPSL", n, (x, y)) for x, y in ((0.10, 0.10), (0.10, 0.20), (0.20, 0.20)) for n in (10, 20, 30)]
    pols += [("FBP", n, (x, r)) for x, r in ((0.5, 0.0), (1.0, 0.05)) for n in (10, 20, 30)]
    rows = []
    for i, a, b, xt, inside in lots:
        L = LOTS[i]; dc = DCC[a:b].astype(np.float64); bu = BU[a:b]; so = SO[a:b].astype(np.float64)
        s0 = -(L["cc"] - L["slot"] * X.SMS)
        rr = dict(i=i, day=L["day"], t=L["t"], add=L["add"], hold=xt, cost=L["cost"], pnl=L["pnl"], inside=inside)
        for fol, V in ((1.0, VX), (0.9, VX9)):
            v = V[a:b].astype(np.float64)
            for kind, N, prm in pols:
                if kind == "ACT":
                    val = (v[ex[i] - 1] - 1) * L["cost"] if inside else L["pnl"]
                else:
                    val = (pol_val(v, dc, bu, so * (fol if True else 1), s0, N, kind, prm) - 1) * L["cost"]
                rr[(kind, N, prm, fol)] = val
        rows.append(rr)
    pickle.dump(dict(pols=pols, rows=rows), open(f"{X.OUT}/x8_rows.pkl", "wb"))
    def hb(h):
        s = h / 1000
        return "<2 s" if s < 2 else "2-15 s" if s < 15 else "15-60 s" if s < 60 else ">60 s"
    grp = collections.defaultdict(list)
    for r in rows: grp[hb(r["hold"])].append(r)
    P(f"\n## B. Uniform exits on ALL his non-DEAD lots ({len(rows):,}), exact replay of each lot alone, SOL over 10-22..10-28 (tape)")
    P("Columns = his ACTUAL hold group (selection by what happened after the buy); a row = one exit rule applied to every lot.")
    hg = ("<2 s", "2-15 s", "15-60 s", ">60 s")
    P("| policy | " + " | ".join(f"{g} ({len(grp[g]):,})" for g in hg) + " | all | all, 0.9 followers |"); P("|---|---|---|---|---|---|---|")
    P(f"| his real P&L (tape) | " + " | ".join(f"{sum(r['pnl'] for r in grp[g]):+.1f}" for g in hg) + f" | {sum(r['pnl'] for r in rows):+.1f} | |")
    for kind, N, prm in pols:
        k1 = (kind, N, prm, 1.0); k9 = (kind, N, prm, 0.9)
        nm = "ACT (his exit, replayed)" if kind == "ACT" else f"{kind} N={N}" + (f" {prm}" if prm is not None else "")
        P(f"| {nm} | " + " | ".join(f"{sum(r[k1] for r in grp[g]):+.1f}" for g in hg) + f" | {sum(r[k1] for r in rows):+.1f} | {sum(r[k9] for r in rows):+.1f} |")
    # per day for a few
    P("\n## B2. per day (all non-DEAD lots), SOL")
    days = sorted(set(r["day"] for r in rows))
    sel = [("ACT", None, None), ("T", 3, None), ("T", 5, None), ("T", 10, None), ("T", 20, None), ("FB", 10, 0.5), ("FB", 20, 1.0), ("TP", 20, 0.10), ("TPSL", 20, (0.10, 0.20))]
    P("| policy | " + " | ".join(f"D{d}" for d in days) + " |"); P("|---|" + "---|" * len(days))
    for kind, N, prm in sel:
        k1 = (kind, N, prm, 1.0)
        P(f"| {kind} {N or ''} {prm if prm is not None else ''} | " + " | ".join(f"{sum(r[k1] for r in rows if r['day'] == d):+.1f}" for d in days) + " |")
    # adds vs not
    P("\n## B3. first lots vs ADD lots (all days), SOL")
    for nm, f in (("first lots", lambda r: not r["add"]), ("ADD lots", lambda r: r["add"])):
        v = [r for r in rows if f(r)]
        P(f"- {nm} ({len(v):,}): real {sum(r['pnl'] for r in v):+.1f}; " + "; ".join(f"{k[0]} {k[1] or ''} {k[2] if k[2] is not None else ''}: {sum(r[(k[0], k[1], k[2], 1.0)] for r in v):+.1f}" for k in sel))
    open(f"{X.OUT}/x8.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

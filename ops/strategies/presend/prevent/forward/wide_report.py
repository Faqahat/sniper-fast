#!/usr/bin/env python3
"""WIDE SELECTION report (dip30 --presend-wide-pct; owner 10-30 ~20:40 PKT: "prepare a proper realistic logging for this in the next
run, we will test this too"). Read-only on a local copy of a run's records (.jsonl).

What it scores: the wide shadow's windows = a wallet's FIRST >= 3% crossing that holds WIDE..MAIN % at that buy (below the live
whale threshold, so the live engine never trades them). Each is scored by the main shadow's own model (row c: the 0.88x limit,
its landing delay, exit, costs = net_cheap), scaled to the live size.

How it is made realistic: on the SAME run, the main shadow's row c is paired with what the live engine really did on the same T2
triggers (live realized P&L, or 0 when the live engine never filled). The mean per-window gap (live - paper) is the CALIBRATION;
the wide windows get the same per-window correction (additive, per fill of row c). Then the live engine's offline-checkable skips
are applied (age-1 / create-slot: age_slots < 2). QUIET and the 10-sec skip need live state and are NOT applied (stated).
Reported: raw paper, calibrated, calibrated without its top 5, and per holding band.
usage: wide_report.py RUN.jsonl"""
import sys, json, collections, os

path = sys.argv[1]
sh_w, sh_exit, sh_size = {}, {}, {}                     # main shadow: trigger sig -> w; w -> row c net; w -> row c size
wa, wx, wsize = {}, {}, {}                              # wide shadow: w -> arm rec; w -> row c net; w -> row c size
live_sig, live_real, live_size = {}, {}, None           # live T2: w -> trigger sig; w -> realized SOL
for line in open(path, errors="replace"):
    if '"ev":"presend_' not in line: continue
    d = json.loads(line); e = d["ev"]
    if e == "presend_arm": sh_w[d["sig"]] = d.get("w")
    elif e == "presend_exit" and d.get("row") == "c": sh_exit[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
    elif e == "presend_fill" and d.get("row") == "c" and "entry" in d: sh_size.setdefault(d["w"], d["entry"].get("sol_in", 0) / 1e9)
    elif e == "presend_wide_arm": wa[d["w"]] = d
    elif e == "presend_wide_exit" and d.get("row") == "c": wx[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
    elif e == "presend_wide_fill" and d.get("row") == "c" and "entry" in d: wsize.setdefault(d["w"], d["entry"].get("sol_in", 0) / 1e9)
    elif e == "presend_live_arm" and d.get("kind", "t2") == "t2":
        live_sig[d["w"]] = d["trig"]["sig"]
        if live_size is None: live_size = d.get("spend", 0) / 1e9 or None
    elif e == "presend_live_realized": live_real[d["w"]] = live_real.get(d["w"], 0.0) + d["pnl"] / 1e9

def scale(p, size): return p * ((live_size / size) if live_size and size else 1.0)

# calibration: main shadow row c fills vs the live engine on the same triggers
pairs = []
for lw, sig in live_sig.items():
    w = sh_w.get(sig)
    if w is None or w not in sh_exit: continue
    pairs.append((scale(sh_exit[w], sh_size.get(w)), live_real.get(lw, 0.0)))
gap = sum(r - p for p, r in pairs) / len(pairs) if pairs else 0.0

rows = []                                               # (pct, paper, calibrated, age_slots)
for w, a in wa.items():
    if w not in wx: continue
    p = scale(wx[w], wsize.get(w))
    rows.append((a.get("pct", 0.0), p, p + gap, a.get("age_slots", 0)))
kept = [r for r in rows if r[3] >= 2]

def summ(rs):
    if not rs: return "n 0"
    cal = sorted((r[2] for r in rs), reverse=True)
    return (f"n {len(rs):4d} | paper {sum(r[1] for r in rs):+8.3f} | calibrated {sum(cal):+8.3f} (win {sum(1 for x in cal if x > 0) / len(cal):.0%}) "
            f"| calibrated w/o top 5 {sum(cal[5:]):+8.3f}")

print(f"WIDE SELECTION {os.path.basename(path)}: {len(wa)} wide windows armed, {len(rows)} filled + exited (row c), live size {live_size} SOL")
print(f"calibration (main shadow row c vs live, same T2 triggers): {len(pairs)} pairs, paper {sum(p for p, _ in pairs):+.3f} vs live {sum(r for _, r in pairs):+.3f} "
      f"-> {gap * 1000:+.2f} mSOL per window")
print(f"all wide fills                 {summ(rows)}")
print(f"after age-1/create-slot skips  {summ(kept)}   (QUIET and 10-sec skip not applied: need live state)")
for lo, hi in ((3, 4), (4, 5), (5, 6)):
    print(f"  holding {lo}-{hi}%               {summ([r for r in kept if lo <= r[0] < hi])}")

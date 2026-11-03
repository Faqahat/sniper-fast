#!/usr/bin/env python3
"""What the pre-send arm filters saved in a run: every live SKIP (young_age = the age-1 skip, quiet = QUIET's arm rule, create_slot, ...)
matched by trigger signature to the SHADOW's window on the same trigger (presend_arm -> presend_exit, row c), whose paper P&L is
scaled from the shadow size to the live size. saved = -(paper P&L of the skipped windows). PAPER ESTIMATE (the shadow's curve
model, no followers cut); failed-try fees of the skipped windows are not counted (small). Read-only.
usage: filter_savings.py RUN.jsonl [--live-size 0.696]"""
import sys, json, collections

path = sys.argv[1]
live = float(sys.argv[sys.argv.index("--live-size") + 1]) if "--live-size" in sys.argv else None
arm_w, exit_c, size_c, skips = {}, {}, {}, []
for line in open(path, errors="replace"):
    if '"ev":"presend_' not in line: continue
    d = json.loads(line); e = d["ev"]
    if e == "presend_arm": arm_w[d["sig"]] = d.get("w")
    elif e == "presend_exit" and d.get("row") == "c": exit_c[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
    elif e == "presend_fill" and d.get("row", "c") == "c" and "entry" in d: size_c.setdefault(d.get("w"), d["entry"].get("sol_in", 0) / 1e9)
    elif e == "presend_live_skip":
        # dip26: re-arm skips ("kind":"rearm") have no T2 trigger: counted apart, not matched to the T2 shadow
        if d.get("kind") == "rearm" or "trig" not in d: skips.append(("rearm:" + str(d.get("why")), None)); continue
        skips.append((d.get("why") or ("quiet" if d.get("quiet_skip") else "?"), d["trig"]["sig"]))
    elif e == "presend_live_arm" and live is None and d.get("kind") != "rearm": live = d.get("spend", 0) / 1e9 or None
agg = collections.defaultdict(lambda: [0, 0, 0, 0, 0.0])   # skips, matched, fills, winners, paper P&L at live size
for why, sig in skips:
    a = agg[why]; a[0] += 1
    w = arm_w.get(sig) if sig is not None else None
    if w is None: continue
    a[1] += 1
    if w in exit_c:
        p = exit_c[w] * ((live / size_c[w]) if live and size_c.get(w) else 1.0)
        a[2] += 1; a[3] += p > 0; a[4] += p
print(f"filter savings (paper, shadow row c scaled to {live or '?'} SOL; saved = minus the skipped windows' P&L)")
for why, (n, m, f, wn, p) in sorted(agg.items(), key=lambda kv: kv[1][4]):
    print(f"  {why:20s} skips {n:4d} | shadow-matched {m:4d} | would-fill {f:3d} ({wn} win / {f - wn} lose) | paper P&L {p:+.3f} -> saved {-p:+.3f} SOL")

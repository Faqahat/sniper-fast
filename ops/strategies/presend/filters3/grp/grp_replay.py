#!/usr/bin/env python3
"""GROUP RISK enforced AT LANDING (owner 11-03 "yes replay it": what an on-chain check program would add). Read-only.
Rule (fixed 10-30 from r40's losses, before any scoring): at our landing, the holders >= 2% (not us) that look like the safe sell
timer's risky holder (>= 5 holds at risk, hz3 >= 0.3) hold >= 6% together -> the buy reverts. Engine logs it as ann.grp_block (dip30+);
older runs: recomputed from ann.holders the same way filters_report.py does.
Money: a blocked fill saves its realized P&L; it costs one failed try (5,120 lamports). NOT modelled: the window keeps sending and might
fill again later (re-fills), and the chain state at execution can include trades in the same block our feed had not shown (both noted).
usage: grp_replay.py RUN.presend.jsonl [...]"""
import sys, json, collections
FAIL = 5120 / 1e9
def grp(a):
    if "grp_block" in a: return bool(a["grp_block"])
    return sum(h.get("pct", 0) for h in a.get("holders", []) if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3) >= 6.0
tot = collections.Counter(); allv = []
for fn in sys.argv[1:]:
    ann, real, t0, t1, has = {}, {}, None, None, False
    for l in open(fn, errors="replace"):
        if '"ev":"presend_live_fill"' in l:
            d = json.loads(l); k = (d["w"], d["mint"])
            if k not in ann: ann[k] = d.get("ann") or {}
            if d.get("ann") and "holders" in d["ann"]: has = True
            t = d.get("t"); t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        elif '"ev":"presend_live_realized"' in l:
            d = json.loads(l); k = (d["w"], d["mint"]); real[k] = real.get(k, 0) + d["pnl"] / 1e9
    name = fn.split("/")[-1].split(".")[0]
    if not has: print(f"{name}: no holder annotations (rule not computable)"); continue
    v = [real[k] for k, a in ann.items() if k in real and grp(a)]
    hrs = (t1 - t0) / 3.6e12 if t0 and t1 and t1 > t0 else 0
    save = -sum(v) - FAIL * len(v)
    top5 = sorted((-x for x in v), reverse=True)[:5]
    print(f"{name}: {len(real):5d} trades {sum(real.values()):+7.3f} | blocked {len(v):3d} (winners {sum(x > 0 for x in v):2d} {sum(x for x in v if x > 0):+6.3f}, losers {sum(x <= 0 for x in v):2d} {sum(x for x in v if x <= 0):+6.3f}) "
          f"| saves {save:+6.3f}{f' = {save / hrs * 24:+.2f}/day' if hrs > 1 else ''} | w/o its top 5 saves {save - sum(top5):+6.3f}")
    allv += v; tot["n"] += len(real); tot["h"] += hrs
save = -sum(allv) - FAIL * len(allv)
print(f"ALL: blocked {len(allv)} (winners {sum(x > 0 for x in allv)}, losers {sum(x <= 0 for x in allv)}) saves {save:+.3f} over {tot['h']:.1f} h = {save / tot['h'] * 24:+.2f}/day | w/o top 5 {save - sum(sorted((-x for x in allv), reverse=True)[:5]):+.3f} | precision {sum(x <= 0 for x in allv) / max(1, len(allv)):.0%}")

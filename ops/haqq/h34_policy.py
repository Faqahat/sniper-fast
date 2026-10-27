#!/usr/bin/env python3
# H2H step 5 (read-only, local): a causal two-mode policy on OUR 278 live attempts. Fill price <= +5% (uncontested): our 1.3 s exit.
# Fill price above +5% (contested; today these fail the guard): accept up to guard G and hold H slots after the dump (haqq-like timer).
# 0.35 SOL, our tx costs, our own trades removed from the curve; all at our REAL landing spot (no speed change).
import sys, json, numpy as np, collections
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
src = open("/home/moiz/sniper/ops/haqq/h31_decomp.py").read().split("# ---------- 4. P&L accounting, ours")[0].replace('print(', '(lambda *a, **k: None)(')
exec(compile(src, "h31_helpers", "exec"))
R = json.load(open(f"{H.OUT}/h2h_fires.json")); fills = [r for r in R if r["status"] == "fill"]; fails = [r for r in R if r["status"] == "fail"]
base_fill = [sim(r, (r["our_s"], r["our_i"])) for r in fills]; bf = sum(x for x in base_fill if isinstance(x, float))
real_fill = sum(r["our_pnl"] for r in fills if r.get("our_pnl") is not None); fail_fee = sum(r.get("fail_fee", 0) for r in fails)
print(f"our 116 fills, our exit: real {real_fill:+.3f} SOL, replay {bf:+.3f} SOL (replay is {bf - real_fill:+.3f} optimistic); failed-attempt fees today {-fail_fee:+.3f}")
print("contested attempts (our landing price > +5%): accept up to G, hold H slots after the dump (no SL); SOL on those attempts (fills, mean mSOL, win):")
for G in (1.10, 1.17, 1.25, None):
    row = []
    for Hh in (6, 10, 15, 20, 30):
        v = [sim(r, (r["our_s"], r["our_i"]), guard=G, exit_slot=max(r["dump_s"] + Hh, r["our_s"] + 1)) for r in fails]
        ok = [x for x in v if isinstance(x, float)]
        row.append(f"H{Hh:2d}: {sum(ok):+6.2f} ({len(ok)}, {np.mean(ok) * 1000 if ok else 0:+.0f}, {np.mean([x > 0 for x in ok]) if ok else 0:.0%})")
    print(f"   G {str(G):5s} " + " | ".join(row))
# same split on fills: does a longer hold help the uncontested fills? (they are the ones haqq mostly skipped)
row = []
for Hh in (6, 10, 15, 20, 30):
    v = [sim(r, (r["our_s"], r["our_i"]), exit_slot=max(r["dump_s"] + Hh, r["our_s"] + 1)) for r in fills]; ok = [x for x in v if isinstance(x, float)]
    row.append(f"H{Hh:2d}: {sum(ok):+6.2f}")
print("uncontested fills with a fixed hold H after the dump instead: " + " | ".join(row))
# contestation visible at landing: buyers ahead of us within the dump's slot window
print("\nby buyers that landed between the dump and us (all 278 attempts, H 20 / G none for fails, our exit for fills):")
for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 99)):
    s = [r for r in R if lo <= len(r["ahead"]) < hi]
    v = [sim(r, (r["our_s"], r["our_i"]), exit_slot=max(r["dump_s"] + 20, r["our_s"] + 1)) for r in s]; ok = [x for x in v if isinstance(x, float)]
    v2 = [sim(r, (r["our_s"], r["our_i"])) for r in s]; ok2 = [x for x in v2 if isinstance(x, float)]
    print(f"   buyers ahead [{lo},{hi}) n {len(s):3d}: hold 20 slots {sum(ok):+.2f} SOL ({np.mean(ok) * 1000:+.0f} mSOL) | our 1.3 s exit {sum(ok2):+.2f} ({np.mean(ok2) * 1000:+.0f} mSOL) | today we filled {np.mean([r['status'] == 'fill' for r in s]):.0%}")
# split the contested attempts by whether haqq bought the same dump (its selection) - fixed holds, no guard, our landing spot
print("\ncontested attempts split by haqq's choice (no guard, our landing spot, hold H slots after the dump):")
for lab, sel in (("haqq bought it", [r for r in fails if r.get("haqq") == "fill"]), ("haqq failed", [r for r in fails if r.get("haqq") == "fail"]), ("haqq absent", [r for r in fails if r.get("haqq") == "none"])):
    row = []
    for Hh in (6, 10, 15, 20, 30):
        v = [sim(r, (r["our_s"], r["our_i"]), exit_slot=max(r["dump_s"] + Hh, r["our_s"] + 1)) for r in sel]; ok = [x for x in v if isinstance(x, float)]
        row.append(f"H{Hh:2d} {sum(ok):+.2f}")
    v = [sim(r, (r["our_s"], r["our_i"]), exit_slot=max(r["h_exit_s"], r["our_s"] + 1)) for r in sel if r.get("h_exit_s")]; ok = [x for x in v if isinstance(x, float)]
    print(f"   {lab:15s} n {len(sel):3d}: " + " | ".join(row) + (f" | at haqq's own exit slot {sum(ok):+.2f}" if ok else ""))

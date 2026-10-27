#!/usr/bin/env python3
"""PRESEND FILTER: checks of the chosen rule C5 (stop a window at trigger + 6 slots if < 2 other trades since the trigger).
  (a) every removed fill with the proof it was knowable: the filling try's send slot vs the trigger, the other trades the engine had
      seen (up to that try's 'pos') vs the first other trade on the chain after the trigger
  (b) dev at 0.50 SOL (exact replay065 per-trade P&L at 0.50; fees and rent as live); validation at 0.50 INFERRED by scaling
  (c) second-order: triggers the live engine skipped as 'blocked_armed' whose slot falls after a C5 stop (they could have armed)"""
import json, collections, time
import numpy as np
import sim, rules, lv

W = sim.load()
SEND = rules.CANDIDATES[3][3]
assert rules.CANDIDATES[3][0].startswith("C5")
pk = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(t / 1e9 + 18000))
print("(a) removed fills (all runs):")
for w in W:
    if not w["filled"]: continue
    ft = [k for k, t in enumerate(w["X"]["tries"]) if t[4]]
    if not ft or SEND(w, ft[0]): continue
    k = ft[0]; t = w["X"]["tries"][k]
    tape = w["X"]["tape"]; kt = w["X"]["k_trig"]; wh = w["X"]["whale"]
    after = tape[kt + 1:]
    oth = after[(after[:, 3] != wh) & ~np.isin(after[:, 3], list(sim._cache["ours"]))]
    first_oth = int(oth[0, 0] - w["trig_slot"]) if len(oth) else None
    print(f"   {w['run']} {pk(w['t'])} {w['mint'][:8]} net {w['net'] / 1e9:+.4f} nb_after {w.get('y_nb')} | fill try sent at trig+{t[0] - w['trig_slot']} slots, "
          f"knew pos {t[7][0] - w['trig_slot']:+d} slots; others seen {rules.oth_since(w, k)}; first other trade on chain at trig+{first_oth}")
# (b) dev at 0.50
R = json.load(open("/home/moiz/sniper-data/replay065/results.json"))
T = {(t["run"], t["mint"], t["buy_pos"][0], t["buy_pos"][1]): t for t in R["trades"] if t["kind"] == "ps"}
print("\n(b) DEV at 0.50 SOL (fills: exact replay; fees / rent back as live):")
for run in ("ams:r24", "ams:r25"):
    before = after = 0.0; wr = 0; lr = 0
    for w in W:
        if w["run"] != run: continue
        fee = w["fail_fee"] / 1e9
        if w["filled"]:
            t = T[(run.split(":")[1], w["mint"], w["fill_slot"], w["fill_idx"])]
            v50 = t["s50"] + w["rent_back"] / 1e9
        else: v50 = 0.0
        before += v50 - fee
        r1 = sim.evaluate([w], send=SEND)["ALL"]
        kept = w["filled"] and r1.get("fills_kept", 0) > 0
        fee_kept = ((w["net"] / 1e9) if kept else 0.0) - r1["after"]
        after += (v50 if kept else 0.0) - fee_kept
        if w["filled"] and not kept:
            if v50 > 0: wr += 1
            else: lr += 1
    print(f"   {run}: {before:+.3f} -> {after:+.3f} ({after - before:+.3f}) winners removed at 0.50: {wr}, losers {lr}")
# (c) second-order
print("\n(c) live 'blocked_armed' skips that fall after a C5 stop on the same token (could have armed instead):")
stops = collections.defaultdict(list)
for w in W:
    for k, t in enumerate(w["X"]["tries"]):
        if not SEND(w, k): stops[(w["run"], w["seg"], w["mint"])].append((t[0], w["en_slot"])); break
n = collections.Counter()
for run in lv.RUNFILES:
    R_ = lv.load(run)
    for s in R_["skips"]:
        if s.get("why") != "blocked_armed": continue
        for (a, en) in stops.get((run, s["seg"], s["trig"]["mint"]), []):
            if a <= s["trig"]["slot"] <= en: n[run] += 1
print("  ", dict(n), "| windows stopped by C5 per run:", dict(collections.Counter(k[0] for k in stops)))

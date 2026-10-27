#!/usr/bin/env python3
"""PRESEND FILTER: the chosen rules at 0.50 SOL.
  DEV: exact replay065 per-trade P&L at 0.50 (followers' limits re-checked; fees, tips, rent, failed tries as live). INFERRED.
  VALIDATION: no exact replay (no decoded follower limits for those runs): a scale estimate, INFERRED:
     net_0.50 = (net_live + FIXED) x 0.50 / spend - FIXED, FIXED = 1.43 mSOL (tips, tx fees, unreturned rent: do not scale).
     Checked against the exact replay on dev below (same formula on the dev fills)."""
import json, collections
import numpy as np
import sim, rules

FIXED = 1_430_000
W = sim.load()
R = json.load(open("/home/moiz/sniper-data/replay065/results.json"))
T = {(t["run"], t["mint"], t["buy_pos"][0], t["buy_pos"][1]): t for t in R["trades"] if t["kind"] == "ps"}
C = {c[0].split()[0]: c for c in rules.CANDIDATES}


def v50(w, exact=True):
    if not w["filled"]: return 0.0
    if exact and w["run"] in ("ams:r24", "ams:r25"):
        return T[(w["run"].split(":")[1], w["mint"], w["fill_slot"], w["fill_idx"])]["s50"] + w["rent_back"] / 1e9
    return ((w["net"] + FIXED) * 500_000_000 / w["spend"] - FIXED) / 1e9


def run_rule(arm, send, exact=True):
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    for w in W:
        r1 = sim.evaluate([w], arm=arm, send=send)["ALL"]
        kept = w["filled"] and r1.get("fills_kept", 0) > 0
        fee_kept = ((w["net"] / 1e9) if kept else 0.0) - r1["after"]
        b = v50(w, exact) - w["fail_fee"] / 1e9; a = (v50(w, exact) if kept else 0.0) - fee_kept
        d = out[w["run"]]; d["before"] += b; d["after"] += a
        if w["filled"] and not kept:
            if v50(w, exact) > 0: d["win_rm"] += 1; d["win_rm_sol"] += v50(w, exact)
            else: d["lose_rm"] += 1
    return out


DEV = ["ams:r24", "ams:r25"]; VAL = ["fra:r23", "fra:r24", "ams:r19", "ams:r20", "fra:r21", "fra:r22"]
chk = run_rule(None, None, exact=False); ex = run_rule(None, None, exact=True)
print("scale-estimate check on dev, no filter: estimate", {r: round(chk[r]["before"], 3) for r in DEV}, "exact", {r: round(ex[r]["before"], 3) for r in DEV})
for name, arm, send in (("C5", None, C["C5"][3]), ("C11", C["C11"][2], None),
                        ("C11+C5", C["C11"][2], C["C5"][3]), ("C2", C["C2"][2], None),
                        ("C5a", None, rules.POSTHOC[0][3]), ("QUIET", rules.quiet_arm, rules.c5_send)):
    o = run_rule(arm, send)
    g = lambda runs: sum(o[r]["after"] - o[r]["before"] for r in runs)
    print(f"{name:8s} at 0.50: " + " ".join(f"{r} {o[r]['before']:+.3f}->{o[r]['after']:+.3f} ({o[r]['after'] - o[r]['before']:+.3f}, win_rm {int(o[r]['win_rm'])})" for r in DEV + VAL)
          + f" | DEV {g(DEV):+.3f} VAL {g(VAL):+.3f}")

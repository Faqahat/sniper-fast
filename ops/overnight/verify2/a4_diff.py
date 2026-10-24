#!/usr/bin/env python3
"""verify2 / a4: per-pick diff, claim (become_eval output) vs my replay (raw tape, opt placement), t8, slip variant."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
R = json.load(open(os.path.join(V.WORK, "v3_res.json")))
CLAIM = {r["m"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
for Lm in ("75", "45"):
    print(f"\n=== L{Lm}: picks where fill status differs (claim vs mine raw|opt), slip variant")
    nd = 0; dsum = 0.0
    for r in R:
        if r["m"] not in CLAIM: continue
        c = CLAIM[r["m"]][Lm]["slip"]; me = r[f"raw|{Lm}|opt"]["slip"]
        cf = bool(c and c["fill"]); mf = bool(me.get("fill"))
        cp = c["pnl"]["t8"] if cf else -0.005; mp = me["pnl"]
        if cf != mf:
            nd += 1; dsum += mp - cp
            print(f"  {r['m'][:10]} {r['name'][:18]:18s} claim {'FILL' if cf else 'fail'} {cp:+.3f} after {(c or {}).get('after')} | mine {'FILL' if mf else 'fail'} {mp:+.3f} ratio {me.get('ratio', 0):.4f} ins {me.get('ins_sig', '')[:8]} | outs {r['n_outs']} seen {r['n_seen']} miss {r['n_miss']} glued {r['glued_n']}")
    print(f"  differing: {nd}, PnL effect mine-claim {dsum:+.3f}")
    print(f"=== L{Lm}: both fill, |pnl diff| > 0.005")
    big = []
    for r in R:
        if r["m"] not in CLAIM: continue
        c = CLAIM[r["m"]][Lm]["slip"]; me = r[f"raw|{Lm}|opt"]["slip"]
        if c and c["fill"] and me.get("fill"):
            d = me["pnl"] - c["pnl"]["t8"]
            if abs(d) > 0.005: big.append((d, r["m"][:10], r["name"][:18], c["pnl"]["t8"], me["pnl"], c.get("after"), me.get("ins_sig", "")[:8]))
    for b in sorted(big): print("  %+.3f %s %-18s claim %+.3f mine %+.3f claim_after %s mine_after %s" % b)
    s = sum(b[0] for b in big); print(f"  n {len(big)} sum {s:+.3f}")

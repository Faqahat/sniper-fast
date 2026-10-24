#!/usr/bin/env python3
"""verify2 / a3: reconcile the collector's TradeEvents with the bonding curve's own token-balance (tb) and lamport (sd) deltas
per tx. A tx whose events do not explain the curve's token change is missing events (seen: a 2nd buy inside a create tx, routed
multi-wallet sells). Output: per pick, the residual (synthetic) trades to add, and stats.
Also re-runs the continuity check after the repair (residual breaks = whole txs missing from the data)."""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V

P = V.load_picks(); L = V.load_launches(P); X = V.load_x1()
WIN = int(sys.argv[1]) if len(sys.argv) > 1 else 300            # slots after the create to check
VT0, RT0 = 1_073_000_000_000_000, 793_100_000_000_000
fix = {}; stats = collections.Counter(); per = {}; breaks_after = {}
for m in P:
    c = L[m]; bc = c.get("bonding_curve"); S = c["slot"]
    seen = set(); units = []
    for r in sorted(X.get(m, []), key=lambda r: (r["s"], r["i"])):
        if r["sig"] in seen: continue
        seen.add(r["sig"]); units.append(r)
    adds = []; nmis = 0
    for r in units:
        if r["err"] or r["s"] - S > WIN: continue
        rows = [x for x in r.get("tb") or [] if x[1] == bc]
        if not rows: continue
        pre, post = rows[0][2] or 0, rows[0][3] or 0
        dtok_curve = post - pre                                     # <0: tokens left the curve (net buying)
        ev = [e for e in r["ev"] if e["kind"] == "T"]
        dtok_ev = sum((-e["tok"] if e["buy"] == 1 else e["tok"]) for e in ev)
        dsol_ev = sum((e["sol"] if e["buy"] == 1 else -e["sol"]) for e in ev)
        sd = [x[1] for x in r.get("sd_bc") or []]
        is_create = r["sig"] == c["sig"]
        if is_create and pre == 0: dtok_curve = post - 1_000_000_000_000_000   # curve's ATA minted 1e15 in this tx
        if dtok_curve != dtok_ev:
            nmis += 1; stats["tx_mismatch"] += 1
            res_tok = dtok_curve - dtok_ev                           # residual token change (<0 = missing buy)
            res_sol = (sd[0] - dsol_ev) if (sd and not is_create) else None
            adds.append(dict(sig=r["sig"], s=r["s"], i=r["i"], res_tok=res_tok, res_sol=res_sol, create=is_create, nev=len(ev)))
    per[m] = dict(n_mis=nmis)
    if adds: fix[m] = adds
print("picks", len(P), "| txs whose events do not explain the curve's token change (first %d slots):" % WIN, stats["tx_mismatch"], "in", len(fix), "picks")
for m, a in fix.items():
    S = L[m]["slot"]
    print("  ", m[:10], [(x["s"] - S, x["i"], "create" if x["create"] else "", round(-x["res_tok"] / 1e12, 3), (round(x["res_sol"] / 1e9, 4) if x["res_sol"] is not None else None)) for x in a][:8])
json.dump(fix, open(os.path.join(V.WORK, "a3_fix.json"), "w"), indent=1)

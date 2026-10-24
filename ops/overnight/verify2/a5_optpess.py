#!/usr/bin/env python3
"""verify2 / a5: what are the unseen txs that separate optimistic and pessimistic placement? (75 and 45 ms, repaired tape)"""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
PRO, SNIPER = V.load_wallet_sets()
R = {r["m"]: r for r in json.load(open(os.path.join(V.WORK, "v3_res.json")))}
for Lm in (75, 45):
    print(f"\n=== L{Lm}: fills under opt whose pess placement differs")
    agg = collections.Counter(); dp = 0.0
    for m in P:
        r = R[m]; a = r[f"rep|{Lm}|opt"]["slip"]; b = r[f"rep|{Lm}|pess"]["slip"]
        if not a.get("fill"): continue
        M = V.Mint(m, L[m], X[m], repair=True)
        outs = V.parse_outs(O[m]["outs"]); seen, miss, how = V.match_anchors(M, outs)
        ia = V.place(M, seen, Lm, "opt"); ib = V.place(M, seen, Lm, "pess")
        if ia == ib: continue
        desc = []
        for u in range(ia + 1, ib + 1):
            x = M.units[u]; ev = [t for t in M.trades if t["u"] == u]
            if x["err"]: kind = "failed"
            elif not ev: kind = "no-trade"
            else: kind = "+".join(("B" if t["buy"] else "S") for t in ev)
            who = (x["signers"] or ["?"])[0]
            tag = "insider" if who in M.insiders or any(t["user"] in M.insiders for t in ev) else ("pro" if who in PRO else ("sniper" if who in SNIPER else "other"))
            sol = sum((t["sol"] if t["buy"] else -t["sol"]) for t in ev) / 1e9
            agg[(kind if kind in ("failed", "no-trade") else ("buys" if sol > 0 else "sells"), tag)] += 1
            desc.append(f"{x['s'] - M.S}/{x['i']} {kind} {tag} {sol:+.3f}")
        dp += (b["pnl"] - a["pnl"])
        first_after = min([ms for u, ms in seen.items() if ms >= Lm] or [None]) if seen else None
        print(f"  {m[:10]} opt {a['pnl']:+.3f} -> pess {('FAIL' if not b.get('fill') else '%+.3f' % b['pnl'])} ratio {b.get('ratio', 0):.3f} | between: {'; '.join(desc[:6])}{' ...' if len(desc) > 6 else ''}")
    print("  unseen units between opt and pess:", dict(agg), " PnL effect %+.3f" % dp)

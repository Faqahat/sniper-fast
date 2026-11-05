#!/usr/bin/env python3
"""WHALEFLIP step 8: DIRECT effect of the whale check on ALL live T2 fills, incl. the ones the raw recording does not cover
(r42 after 11-01 19:06 PKT, r43), using the ENGINE's own view of the whale's holding at our landing (presend_live_fill ann.holders:
holders >= 2% just before our buy, from the engine's detector; whale absent = < 2% = treated as sold) [PROXY]. Checked against the
exact tape balance on covered fills (the engine tracks the fee payer; whales selling through another fee payer look like holders).
Direct = minus the realized P&L of the blocked fills (no re-fill, no fees).  usage: w8_proxy.py PERIODS X"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W
pers = sys.argv[1].split(","); X = float(sys.argv[2])
F = [f for f in W.load() if f["kind"] == "t2" and f["period"] in pers]
EX = {(r["run"], r["ses"], r["w"]): r for r in json.load(open(f"{W.D}/exact.json"))}
g = collections.defaultdict(list); agree = collections.Counter()
for f in F:
    ann = f["fills"][0].get("ann") or {}
    wh = f["trig"]["wallet"]; b0 = f["trig"]["bal"] / 1e13
    hp = [z["pct"] for z in ann.get("holders", []) if z["w"] == wh]
    pf = (hp[0] / b0) if hp else 0.0
    blk_p = pf > X
    e = EX.get((f["run"], f["ses"], f["w"]))
    cov = bool(e and e["covered"])
    if cov:
        blk_e = not e.get("wh_closed") and (e.get("wh_frac") or 0) > X
        agree[(blk_p, blk_e)] += 1
    g[(f["seg"], cov, blk_p)].append(f["pnl"])
print(f"X {X}: proxy block vs exact block on covered fills (proxy, exact): {dict(agree)}")
for s in sorted({k[0] for k in g}):
    for cov in (True, False):
        b = g.get((s, cov, True), []); k = g.get((s, cov, False), [])
        if not b and not k: continue
        print(f"  {s:5s} {'covered  ' if cov else 'UNCOVERED'} blocked n {len(b):4d} live P&L {sum(b):+.3f} -> direct {-sum(b):+.3f} (losers {sum(1 for x in b if x < 0)}) | kept n {len(k)} {sum(k):+.3f}")
for cov in (True, False):
    b = [x for (s, c, bl), v in g.items() if c == cov and bl for x in v]
    print(f"  ALL {'covered' if cov else 'UNCOVERED'}: blocked {len(b)} direct {-sum(b):+.3f}, w/o top5 gains {-sum(sorted(b, reverse=False)[5:]) if len(b) > 5 else 0:+.3f}")

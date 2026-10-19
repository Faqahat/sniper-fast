#!/usr/bin/env python3
"""READ-ONLY: check the engine's rule #2 decisions (RACE decide lines, --race-glued) against the chain, for EVERY decided
launch (passes and rejects). Chain: glued run = non-vote txs right after the create that are OK with a buy TradeEvent
of the mint (race_lib); gsol = sum of TradeEvent sol. Tip: the create tx's System-transfer destinations (common.tx_summary
tips), lunar = a destination starting with "moon". Rule #2 on chain: glued >= 1, 3 <= gsol <= 5 SOL, lunar tip, dev
0.5..8, create_v2, host ok. Usage: verify_g.py PAPER_LOG [max_launches]"""
import sys, re, collections
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap
tm = load_tipmap()
log = sys.argv[1]; MAX = int(sys.argv[2]) if len(sys.argv) > 2 else 400
dec = {}; fired = set()
for l in open(log, errors="replace"):
    m = re.search(r"RACE decide slot=(\d+) mint=(\w+) at_ms=([\d.]+).* bundle_n=(\d+) bundle_sol=([\d.]+) glued_closed=(\w+) glued_unknown=(\d+) order=(\w+).* pass=(\w+)", l)
    if m: dec[m.group(2)] = dict(slot=int(m.group(1)), at=float(m.group(3)), n=int(m.group(4)), sol=float(m.group(5)), closed=m.group(6) == "true",
                                 unk=int(m.group(7)), order=m.group(8), passed=m.group(9) == "true")
    m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+)", l)
    if m: fired.add(m.group(2))
print(f"decided launches: {len(dec)} (pass {sum(d['passed'] for d in dec.values())}), fired in paper: {len(fired)}")
rows = []; cache = {}
for mint, d in list(dec.items())[-MAX:]:
    blk = cache.get(d["slot"]) or get_block(d["slot"]); cache[d["slot"]] = blk
    if not isinstance(blk, dict) or "transactions" not in blk: rows.append((mint, d, None)); continue
    txs = [t for t in blk["transactions"] if not is_vote(t)]
    res = None
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        if meta.get("err") is not None: continue
        tr, cr = events(meta.get("logMessages"))
        if not [x for x in cr if x["mint"] == mint]: continue
        glued, gsol = 0, 0
        for t2 in txs[i + 1:]:
            m2 = t2.get("meta") or {}
            tr2, _ = events(m2.get("logMessages")) if m2.get("err") is None else ([], [])
            b = [e for e in tr2 if e["mint"] == mint and e["buy"]]
            if m2.get("err") is None and b: glued += 1; gsol += sum(e["sol"] for e in b) / 1e9
            else: break
        s, _ = tx_summary(t, tm)
        lunar = any(str(x[2]).startswith("moon") for x in s["tips"])
        res = dict(glued=glued, gsol=gsol, lunar=lunar)
        break
    rows.append((mint, d, res))
def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
mis = []; err = []; cnt = collections.Counter()
for mint, d, r in rows:
    if r is None: cnt["unverifiable"] += 1; continue
    chain_bundle = r["glued"] >= 1 and 3.0 <= r["gsol"] <= 5.0
    eng_bundle = d["closed"] and d["unk"] == 0 and d["n"] >= 1 and 3.0 <= d["sol"] <= 5.0
    if r["gsol"] > 0 and d["unk"] == 0 and d["closed"]: err.append(abs(d["sol"] - r["gsol"]) / r["gsol"])
    cnt["n match" if d["n"] == r["glued"] else "n differ"] += 1
    if chain_bundle != eng_bundle:
        mis.append((mint, d, r))
print(f"verified {len(rows) - cnt['unverifiable']}: {dict(cnt)}")
print(f"bundle SOL |engine - chain| / chain (closed, no unknown legs, chain gsol>0): median {pct(err,.5)*100:.2f}% p90 {pct(err,.9)*100:.2f}% n={len(err)}")
print(f"BUNDLE-CONDITION MISMATCHES (engine 3..5 SOL glued vs chain): {len(mis)}")
for mint, d, r in mis[:30]:
    print(f"  {mint[:10]} slot {d['slot']}: engine n={d['n']} sol={d['sol']:.3f} closed={d['closed']} unk={d['unk']} order={d['order']} pass={d['passed']} | chain glued={r['glued']} gsol={r['gsol']:.3f} lunar={r['lunar']}")
fp = [(m, d, r) for m, d, r in rows if r and d["passed"]]
bad = [x for x in fp if not (x[2]["glued"] >= 1 and 3.0 <= x[2]["gsol"] <= 5.0 and x[2]["lunar"])]
print(f"\nENGINE PASSES: {len(fp)}; failing rule #2 on chain (bundle or tip): {len(bad)}")
for mint, d, r in fp: print(f"  {mint[:10]} slot {d['slot']} engine n={d['n']} sol={d['sol']:.3f} at {d['at']:.1f} ms | chain glued={r['glued']} gsol={r['gsol']:.3f} lunar={r['lunar']}")
at = [d["at"] for d in dec.values()]
print(f"\ndecision time after first sight (ms): p50 {pct(at,.5):.1f} p90 {pct(at,.9):.1f} max {max(at) if at else 0:.1f}; closed {sum(d['closed'] for d in dec.values())}/{len(dec)}, order found {sum(d['order']=='yes' for d in dec.values())}/{len(dec)}, with unknown (CPI) legs {sum(d['unk']>0 for d in dec.values())}")

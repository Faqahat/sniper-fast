#!/usr/bin/env python3
"""verify_dip / hk_real: external reality check. The claim was learned from wallet HkQ7hMjy, a real bot that buys right after
big sells. Its REAL round trips on launch mints (first 720 slots after the create, both runs): SOL out - SOL in incl. pump
fees (from the events), tx fees and tips of its successful txs; its failed txs counted. Also: its entry delay after the
sell (proxy) and hold, to compare with the replayed strategy.
usage: python3 -I -B hk_real.py [wallet]"""
import sys, os, json, gzip, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.path.join(HERE, "work")
W = sys.argv[1] if len(sys.argv) > 1 else "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
tot = collections.Counter(); per = []; nfail = 0; holds = []
for tag in ("R1", "R2"):
    for b in range(256):
        data = json.load(gzip.open(os.path.join(WORK, tag, f"b{b:03d}.json.gz"), "rt"))
        for m, d in data.items():
            rows = [r for r in d["t"] if r[6] == W and not r[4]]
            nfail += sum(1 for f in d["f"] if f[2] == W)
            if not rows: continue
            seen = set(); tok = 0; sol_in = 0; sol_out = 0; fees = 0; slots = []
            for r in rows:
                if (r[3], r[2]) in seen: continue
                seen.add((r[3], r[2]))
                pf = (r[15] or 0) + (r[17] or 0)
                if r[9] == 1: tok += r[8]; sol_in += r[7] + pf
                else: tok -= r[8]; sol_out += r[7] - pf
                slots.append((r[0], r[9]))
            txs = {r[3]: r for r in rows}
            fees = sum((r[23] or 0) + (r[25] or 0) for r in txs.values())
            closed = abs(tok) <= 0.001 * max(1, sum(r[8] for r in rows if r[9] == 1))
            per.append(dict(m=m, run=tag, closed=closed, sol_in=sol_in, pnl=(sol_out - sol_in - fees) / 1e9, n=len(txs)))
            if closed and slots:
                bs = [s for s, isb in slots if isb == 1]; ss = [s for s, isb in slots if isb == 0]
                if bs and ss: holds.append(min(ss) - min(bs))
cl = [p for p in per if p["closed"]]
print(f"{W[:8]}: launches traded {len(per)}, closed round trips {len(cl)}; failed txs on these launches (first 720 slots): {nfail}")
for run in ("R1", "R2"):
    v = [p for p in cl if p["run"] == run]
    if v: print(f"  {run}: closed {len(v)}, PnL after pump fees + its tx fees + tips {sum(p['pnl'] for p in v):+.2f} SOL; avg buy {statistics.mean(p['sol_in'] for p in v) / 1e9:.3f} SOL; "
                f"mean PnL/round trip {statistics.mean(p['pnl'] for p in v):+.4f}")
if holds: holds.sort(); n = len(holds); print(f"  hold (first sell slot - first buy slot): p25 {holds[n // 4]} median {holds[n // 2]} p75 {holds[3 * n // 4]} slots")
print(f"  failed-tx cost if each failed tx cost 5000-15000 lamports: {nfail * 5e-6:.2f}-{nfail * 1.5e-5:.2f} SOL")

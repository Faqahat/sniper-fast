#!/usr/bin/env python3
"""DIPLIMIT step 7: where the change vs 0.12 comes from. Per drop: NEW fills (window not filled live), MOVED fills (live window, other
try fills: modelled exit) vs the live P&L they replace, LOST fills (live window not filled), and fees.  usage: d7_decomp.py LABEL TAG..."""
import sys, json
D = "/home/moiz/sniper-data/filters3/diplimit"
label, tags = sys.argv[1], sys.argv[2:]
rows = []
for t in tags: rows += json.load(open(f"{D}/replay_{t}.json"))["rows"]
print(f"== {label}")
for dr in ("0.06", "0.08", "0.1", "0.15", "0.18"):
    new = [r for r in rows if not r["live_filled"] and r["d"][dr]["filled"] > 0]
    lf = [r for r in rows if r["live_filled"]]
    kept = [r for r in lf if r["d"][dr]["src"].get("live", 0) == sum(r["d"][dr]["src"].values())]
    other = [r for r in lf if r not in kept]
    nn = sum(r["d"][dr]["filled"] for r in new); ns = sum(r["d"][dr]["fill_pnl"] for r in new)
    nw = sum(1 for r in new if r["d"][dr]["fill_pnl"] > 0)
    os_ = sum(r["d"][dr]["fill_pnl"] for r in other); ol = sum(r["pnl_live"] for r in other)
    lostn = sum(1 - r["d"][dr]["filled"] for r in other)
    fee = sum(r["d"][dr]["fails"] - r["d"]["0.12"]["fails"] for r in rows) * 5120e-9
    print(f" {float(dr):.2f}: NEW fills {nn:5.1f} P&L {ns:+.3f} (win {nw / max(1, len(new)):.0%}) | live windows changed {len(other):3d}: live {ol:+.3f} -> {os_:+.3f} "
          f"(of which unfilled {lostn:.1f}) | fee change {fee:+.3f} | net vs 0.12 {ns + os_ - ol - fee:+.3f}")

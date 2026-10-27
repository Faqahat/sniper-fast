#!/usr/bin/env python3
# H2H step 4 (read-only, local): the CONTESTED dumps (we failed the +5% guard, haqq filled): entry spot x exit, 0.35 SOL, our tx costs.
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
import importlib.util
spec = importlib.util.spec_from_file_location("h31", "/home/moiz/sniper/ops/haqq/h31_decomp.py")
src = open("/home/moiz/sniper/ops/haqq/h31_decomp.py").read().split("# ---------- 4. P&L accounting, ours")[0]
src = src.replace('print(', '(lambda *a, **k: None)(')                 # reuse the helpers (sim, tape) silently
exec(compile(src, "h31_helpers", "exec"))
R = json.load(open(f"{H.OUT}/h2h_fires.json"))
cont = [r for r in R if r["status"] == "fail" and r.get("haqq") == "fill" and r.get("h_exit_s")]
def tot(v): ok = [x for x in v if isinstance(x, float)]; return len(ok), sum(ok)
rows = [("haqq real (its size, its costs)", (len(cont), sum(r["h_pnl"] for r in cont if r.get("h_pnl") is not None)))]
rows.append(("haqq's spot, its exit slot", tot([sim(r, (r["h_s"], r["h_i"]), exit_slot=r["h_exit_s"]) for r in cont])))
rows.append(("haqq's spot, our exit (5 slots / SL)", tot([sim(r, (r["h_s"], r["h_i"])) for r in cont])))
rows.append(("our spot (no guard), haqq's exit slot", tot([sim(r, (r["our_s"], r["our_i"]), exit_slot=max(r["h_exit_s"], r["our_s"] + 1)) for r in cont])))
rows.append(("our spot (no guard), our exit", tot([sim(r, (r["our_s"], r["our_i"])) for r in cont])))
print(f"contested dumps (we failed the guard, haqq filled): {len(cont)}; 0.35 SOL, our tx costs (buy {BUY_TX:.4f} + sell {SELL_TX:.4f})")
for lab, (n, v) in rows: print(f"   {lab:40s} n {n:3d}: {v:+.3f} SOL ({v / max(n, 1) * 1000:+.1f} mSOL each)")

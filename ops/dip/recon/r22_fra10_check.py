#!/usr/bin/env python3
# r22: FRA run 10 (4 s hold) fills checked on the REAL tape (our real buy in place, no counterfactual): the SOL our real tokens
# would have fetched at slot +5 / +4 (index 148) vs what our real sell at slot +18 got. Pump fees in; tx costs equal in both.
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
P = json.load(open(f"{R.WORK}/pertrade.json")); TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
rows = []
for o in P:
    if not (o["srv"] == "FRA" and o["run"] in (10, 11) and o["live_fill"] and o.get("sell_slot")): continue
    TP = TPS[o["tape"]]; t = TP.mint2t[o["mint"]]; tp = TP.token(t)
    q = float(o["live_tok"]); s_in = o["land_slot"]
    def real_val(key):
        V = T = None; fr = None
        for y in range(tp["n"]):
            if tp["SI"][y] >= key: break
            if tp["SI"][y] >= s_in * 100000 + o["land_idx"]:
                V = float(tp["vsol"][y]); T = float(tp["vtok"][y]); fr = float(tp["fr"][y])
        return V * q / (T + q) * (1 - fr) / 1e9
    v5 = real_val((s_in + 5) * 100000 + 148); v4 = real_val((s_in + 4) * 100000 + 148)
    rows.append((o["mint"][:6], o["size"], o["sell_received"], v5, v4, o["chain_pnl"], o["exit_why_live"], o["exit_off_live"]))
a = np.array([[r[2], r[3], r[4], r[5]] for r in rows])
print(f"FRA r10+r11 fills {len(rows)}: real sell got {a[:, 0].sum():.3f} SOL | real tape value at slot +5: {a[:, 1].sum():.3f} | at +4: {a[:, 2].sum():.3f} | "
      f"difference +5 vs real {a[:, 1].sum() - a[:, 0].sum():+.3f} SOL; live chain P&L {a[:, 3].sum():+.3f}")
for r in rows: print(f"   {r[0]} size {r[1]:.2f} sold {r[2]:.4f} (exit {r[6]} +{r[7]}) | at +5 {r[3]:.4f} | at +4 {r[4]:.4f} | live {r[5]:+.4f}")

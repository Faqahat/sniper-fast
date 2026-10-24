#!/usr/bin/env python3
# Exit comparison on our LIVE fills (owner 10-24: "we will calculate these again with run 4's"). For every fill of the given run
# records: our buy located on the collector's tape, then each exit simulated on the real trades after it (TP / SL checked after
# every trade, the sell lands one slot after the trigger; time limit = landing slot + 6), P&L vs our cost incl. pump fees,
# tips excluded. Splits = half of the position on each exit.
# usage: RP_PHASEA_R3=<extracted window> python3 -I exit_live_sim.py dip_r1.jsonl dip_r2.jsonl ...
import os, sys, json
os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3tp"); os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
os.environ.update(SELL_LAT="75", DIP_LATS="35,50,75", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
US = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
EX = {"TP +5% (now)": (0.05, 0.10), "TP +10%": (0.10, 0.10), "TP +20%": (0.20, 0.10), "no TP, sell 1.3 s": (9, 0.10)}
fills = []
for p in sys.argv[1:]:
    ev = [json.loads(l) for l in open(p)]
    for f in [e for e in ev if e["ev"] == "fire"]:
        bl = next((e for e in ev if e["ev"] == "buy_land" and e.get("sig") == f["buy_sig"]), None)
        cl = next((e for e in ev if e["ev"] == "close" and e.get("buy_sig") == f["buy_sig"]), None)
        if bl and cl: fills.append((os.path.basename(p)[:6], f["mint"], bl, cl))
splits = {"half TP5 + half 1.3 s": ("TP +5% (now)", "no TP, sell 1.3 s"), "half TP10 + half 1.3 s": ("TP +10%", "no TP, sell 1.3 s")}
tot = {k: 0.0 for k in list(EX) + list(splits)}; n = 0
print(f"{'run':6s} {'token':7s} " + " ".join(f"{k:>19s}" for k in EX))
for p, m, bl, cl in fills:
    L = X.L.get(m); tr = X.rp.read_bucket(L["run"], X.rp.bucket(m), {m}).get(m) if L else None
    kb = next((k for k, t in enumerate(tr or []) if t.get("user") == US and t["buy"] and t["s"] == bl["slot"]), None)
    if kb is None: print(f"{p} {m[:6]}: not on the collector tape (sync / extract the window first)"); continue
    b = tr[kb]; tok = b["tok"]; fr = ((b.get("fbps") or 95) + (b.get("cbps") or 30)) / 1e4; cost = b["sol"] / 1e9 * (1 + fr); size = b["sol"] / 1e9
    def val(t): k = t["vsol"] * t["vtok"]; return (t["vsol"] - k / (t["vtok"] + tok)) / 1e9 * (1 - fr) / cost - 1
    later = [t for t in tr[kb + 1:] if t.get("user") != US]; deadline = b["s"] + 6
    def sim(tp, sl):
        for t in later:
            if t["s"] >= deadline: break
            v = val(t)
            if v >= tp or v <= -sl:
                nxt = next((u for u in later if u["s"] >= t["s"] + 1), None)
                return val(nxt) if nxt else v
        last = [t for t in later if t["s"] < deadline]
        return val(last[-1]) if last else 0.0
    res = {k: sim(*v) for k, v in EX.items()}; n += 1
    for k, v in res.items(): tot[k] += v * size
    for k, (a, c) in splits.items(): tot[k] += 0.5 * (res[a] + res[c]) * size
    print(f"{p:6s} {m[:6]:7s} " + " ".join(f"{100 * res[k]:+8.1f}% {res[k] * size:+.4f}" for k in EX))
print(f"\nTOTAL over {n} fills (SOL, curve level, tips excluded):")
for k, v in tot.items(): print(f"  {k:28s} {v:+.4f}")

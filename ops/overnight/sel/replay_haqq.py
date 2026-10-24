#!/usr/bin/env python3
# Owner 10-24 06:00 PKT: "replay this [haqqiUUX's way] with our last few wins, simulating our speed".
# For every LIVE fill (runs given): our real buy (exact position on the collector tape), then on the token's REAL later trades:
#   V1 now      : TP +5% / SL -10% / 6 slots (the engine)
#   V2 split    : half V1, half rides: SL -10% from entry, trailing 25% off its peak once >= +20%, max 30 s
#   V3 haqq     : thirds: 1/3 at +30% or 5 s; 1/3 at +60% or 15 s; 1/3 rides (gives back 25 points from its best once that
#                 best is >= +20%, e.g. best +60% -> sold at +35%; max 60 s); safety: everything left is sold at <= -15%
#   V4 haqq+add : V3, plus haqq-style ADDS: each later dump on the token within 60 s of our entry (>= 1 SOL, drop >= 4.65%,
#                 first big sell of its slot, at most 3 adds) -> another buy of the same size at OUR speed (ADD_MS after the
#                 dump in block position, default 40 ms; must land by dump slot + 1) only if the price is <= +5% over the
#                 post-dump price (our guard); each add exits by the V3 rule from its own entry.
# A trigger at a trade sells on the first trade >= 1 slot later (our sell landing); values = constant-product sell-out of that
# piece's tokens minus pump fee, vs its cost (SOL in + pump fee). Costs: every extra buy -0.0027 SOL (fee + tips), every extra
# sell -0.0016 (fee + fallback tip); our own extra buys/sells are not fed back into the curve (small sizes vs the flow).
import os, sys, json
os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3all"); os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
os.environ.update(SELL_LAT="75", DIP_LATS="35,50,75", DIP_B="0.35", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import selexit2 as X
US = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"; ADD_MS = float(os.environ.get("ADD_MS", "40")); BUYC, SELLC = 0.0027, 0.0016
chain = {}
for lg in sys.argv[1:]:
    p = lg.replace(".jsonl", ".log.realized")
    if os.path.exists(p):
        for l in open(p):
            kv = dict(x.split("=", 1) for x in l.split() if "=" in x)
            if "mint" in kv: chain[kv["mint"]] = float(kv["pnl"])
fills = []
for p in sys.argv[1:]:
    ev = [json.loads(l) for l in open(p)]
    for f in [e for e in ev if e["ev"] == "fire"]:
        bl = next((e for e in ev if e["ev"] == "buy_land" and e.get("sig") == f["buy_sig"]), None)
        cl = next((e for e in ev if e["ev"] == "close" and e.get("buy_sig") == f["buy_sig"]), None)
        if bl and cl: fills.append((os.path.basename(p)[:6], f["mint"], bl))

def piece_value(t, tok, fr, cost):
    k = t["vsol"] * t["vtok"]; return (t["vsol"] - k / (t["vtok"] + tok)) / 1e9 * (1 - fr) / cost - 1

def run_rule(later, start_s, a0, tok, fr, cost, rule):
    """P&L (fraction of cost) of one position of `tok` tokens under an exit rule; later = trades after its entry"""
    def sell_at(i):                       # first trade >= 1 slot after trade i (our sell landing)
        nxt = next((u for u in later[i + 1:] if u["s"] >= later[i]["s"] + 1), None)
        return piece_value(nxt or later[i], tok, fr, cost)
    if not later: return 0.0, 1
    if rule == "v1":
        for i, t in enumerate(later):
            if t["s"] >= start_s + 6: return piece_value(later[i - 1] if i else t, tok, fr, cost), 1
            v = piece_value(t, tok, fr, cost)
            if v >= 0.05 or v <= -0.10: return sell_at(i), 1
        return piece_value(later[-1], tok, fr, cost), 1
    if rule == "ride30" or rule == "ride60":
        cap, sl = (30_000, 0.10) if rule == "ride30" else (60_000, 0.15); peak = -9
        for i, t in enumerate(later):
            if X.arr(t) - a0 > cap: return piece_value(later[i - 1] if i else t, tok, fr, cost), 1
            v = piece_value(t, tok, fr, cost); peak = max(peak, v)
            if v <= -sl or (peak >= 0.20 and v <= peak - 0.25): return sell_at(i), 1
        return piece_value(later[-1], tok, fr, cost), 1
    if rule in ("tp30_5s", "tp60_15s"):
        tp, cap = (0.30, 5_000) if rule == "tp30_5s" else (0.60, 15_000)
        for i, t in enumerate(later):
            if X.arr(t) - a0 > cap: return piece_value(later[i - 1] if i else t, tok, fr, cost), 1
            v = piece_value(t, tok, fr, cost)
            if v >= tp or v <= -0.15: return sell_at(i), 1
        return piece_value(later[-1], tok, fr, cost), 1
    raise ValueError(rule)

def v3(later, start_s, a0, tok, fr, cost):
    parts = [run_rule(later, start_s, a0, tok / 3, fr, cost / 3, r) for r in ("tp30_5s", "tp60_15s", "ride60")]
    return sum(p for p, _ in parts) / 3, 3

out = []
for run, m, bl in fills:
    L = X.L.get(m); tr = X.rp.read_bucket(L["run"], X.rp.bucket(m), {m}).get(m) if L else None
    kb = next((k for k, t in enumerate(tr or []) if t.get("user") == US and t["buy"] and t["s"] == bl["slot"]), None)
    if kb is None: print(f"{run} {m[:6]}: not on the collector tape"); continue
    b = tr[kb]; tok = b["tok"]; fr = ((b.get("fbps") or 95) + (b.get("cbps") or 30)) / 1e4; size = b["sol"] / 1e9; cost = size * (1 + fr); a0 = X.arr(b)
    later = [t for t in tr[kb + 1:] if t.get("user") != US]
    r1, _ = run_rule(later, b["s"], a0, tok, fr, cost, "v1")
    rh, _ = run_rule(later, b["s"], a0, tok / 2, fr, cost / 2, "ride30")
    r2 = 0.5 * r1 + 0.5 * rh
    r3, n3 = v3(later, b["s"], a0, tok, fr, cost)
    pnl = {"V1 now": r1 * size, "V2 split": r2 * size - SELLC, "V3 haqq exits": r3 * size - 2 * SELLC}
    # V4: adds on later dumps within 60 s (our speed + guard), each exiting by the V3 rule
    adds = 0; add_pnl = 0.0; last_s = -1
    for j in range(kb + 1, len(tr)):
        t = tr[j]
        if X.arr(t) - a0 > 60_000 or adds >= 3: break
        if t["buy"] or t["sol"] < X.MIN_SELL or t.get("syn") or t.get("user") == US or t["s"] == last_s: continue
        last_s = t["s"]; p_after = t["vsol"] / t["vtok"]; ad = X.arr(t)
        p_before = (t["vsol"] + t["sol"]) / max(1, t["vtok"] - t["tok"])
        if p_after / p_before > 1 - 0.0465: continue                        # dump too small (our envelope: drop >= 4.65%)
        ke = j + 1
        while ke < len(tr) and X.arr(tr[ke]) < ad + ADD_MS: ke += 1
        if ke >= len(tr): break
        pre = tr[ke - 1]
        if int((ad + ADD_MS) // X.SMS) > t["s"] + 1: continue               # would land after the slot deadline
        if (pre["vsol"] / pre["vtok"]) / p_after > 1.05: continue           # our guard refuses (fee only)
        xin = int(size * 1e9 / (1 + fr)); q = pre["vtok"] * xin // (pre["vsol"] + xin)
        lat2 = [u for u in tr[ke:] if u.get("user") != US]
        rr, _ = v3(lat2, pre["s"], ad + ADD_MS, q, fr, size * (1 + fr)); add_pnl += rr * size - BUYC - 2 * SELLC; adds += 1
        if os.environ.get("DEBUG"):
            print(f"   add {m[:6]} +{(ad - a0) / 1000:5.1f}s after our buy: dump {t['sol'] / 1e9:5.2f} SOL drop {100 * (1 - p_after / p_before):4.1f}% "
                  f"| entry price vs our first buy {100 * ((pre['vsol'] / pre['vtok']) / (b['vsol'] / b['vtok']) - 1):+6.1f}% | V3 result {100 * rr:+6.1f}% = {rr * size - BUYC - 2 * SELLC:+.4f} SOL")
    pnl["V4 haqq + adds"] = pnl["V3 haqq exits"] + add_pnl
    out.append(dict(run=run, m=m, won=(chain.get(m, r1) > 0), adds=adds, pnl=pnl, chain=chain.get(m)))
keys = ["V1 now", "V2 split", "V3 haqq exits", "V4 haqq + adds"]
print(f"add speed {ADD_MS:.0f} ms after the dump\n{'run':6s} {'token':7s} {'chain':>9s} {'adds':>4s} " + " ".join(f"{k:>15s}" for k in keys))
for o in out: print(f"{o['run']:6s} {o['m'][:6]:7s} {o['chain'] if o['chain'] is not None else 0:+9.4f} {o['adds']:4d} " + " ".join(f"{o['pnl'][k]:+15.4f}" for k in keys))
for lab, sel in (("our WINS", [o for o in out if o["won"]]), ("ALL fills", out)):
    print(f"\n{lab} ({len(sel)} trades), SOL (pump fees + extra tx costs in; our base buy/sell tips excluded as in all variants):")
    for k in keys: print(f"  {k:16s} {sum(o['pnl'][k] for o in sel):+.4f}")

#!/usr/bin/env python3
# VALIDATION 3 (read-only): cross-check the multi-rule replay engine against a simple, separate reference implementation
# (one rule at a time, written independently) on real launches: hold-N-seconds, TP/SL with cap, 2-leg partial ladder.
import sys, json, collections, statistics, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); O = rp.load_obs()
fw = [m for m in O if m in L and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
random.seed(3); samp = random.sample(fw, 1500)
byb = collections.defaultdict(set)
for m in samp: byb[rp.bucket(m)].add(m)
FEE_BUY, SELL_FEE = 0.02, 0.0005
def ref(tr, idx, B, rule):
    V, T = tr[idx - 1]["vsol"], tr[idx - 1]["vtok"]
    fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; p_in = X / q
    s0 = tr[idx - 1]["s"]
    left = q; got = 0.0; nsell = 0
    def sell(k, V, T):
        nonlocal left, got, nsell
        k = min(k, left)
        so = V * k // (T + k); got += so * (1 - fr) / 1e9 - SELL_FEE; left -= k; nsell += 1
        return V - so, T + k
    kind = rule[0]; pend = None; done_leg = set()
    for t in tr[idx:]:
        el = (t["s"] - s0) * rp.SLOT_MS / 1000
        if pend is not None and t["s"] > pend[0]:
            V, T = sell(pend[1], V, T); pend = None
            if left <= 0: break
        if kind == "hold" and el >= rule[1]: V, T = sell(left, V, T); break
        if kind in ("tpsl", "lad") and el > rule[-1]: V, T = sell(left, V, T); break
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        if V >= rp.GRAD_VSOL: V, T = sell(left, V, T); break
        mult = (V / T) / p_in
        if kind == "tpsl" and pend is None and (mult >= rule[1] or (rule[2] and mult <= rule[2])): pend = (t["s"], left)
        if kind == "lad" and pend is None:
            if "a" not in done_leg and mult >= rule[1]: done_leg.add("a"); pend = (t["s"], int(q * 0.5))
            elif "a" in done_leg and "b" not in done_leg and mult >= rule[2]: done_leg.add("b"); pend = (t["s"], left)
    if left > 0: V, T = sell(left, V, T)
    return round(got - B * (1 + FEE_BUY), 6)
rules = [r for r in rp.default_rules() if r["name"] in ("hold5s", "hold30s", "tp1.5_sl0.8_c60", "tp2.0_None_c300", "tp2.0_sl0.7_c300")]
rules.append(rp.R("lad2", [(0.5, ("x", 1.3)), (1.0, ("x", 2.0))], 120))
REF = {"hold5s": ("hold", 5), "hold30s": ("hold", 30), "tp1.5_sl0.8_c60": ("tpsl", 1.5, 0.8, 60), "tp2.0_None_c300": ("tpsl", 2.0, None, 300),
       "tp2.0_sl0.7_c300": ("tpsl", 2.0, 0.7, 300), "lad2": ("lad", 1.3, 2.0, 120)}
diffs = collections.defaultdict(list); n = 0
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or len(tr) < 3: continue
        c = L[m]; st = rp.structure(tr, c); idx, _ = rp.place(tr, c, st, O[m]["outs"], 75)
        if idx < 1 or idx >= len(tr): continue
        out = rp.sim(tr, c, st, idx, 0.5, rules)
        if not out: continue
        n += 1
        for r in rules:
            diffs[r["name"]].append(out[r["name"]]["pnl"] - ref(tr, idx, 0.5, REF[r["name"]]))
print(f"launches compared: {n}")
for k, v in diffs.items():
    bad = [d for d in v if abs(d) > 1e-4]
    print(f"   {k:20} engine - reference: max |diff| {max(abs(d) for d in v):.6f} SOL, cases > 0.0001 SOL: {len(bad)}")

#!/usr/bin/env python3
# Exit sweep 2 (owner 10-24 ~21:55 PKT: "also the SL 5-20%"): time limit x stop-loss on live fills, engine's own tape.
# Each tape trade after our buy updates the curve; value = what our tokens would sell for (gross) / what the same tokens fetch
# right after our buy; the stop fires on the first trade with value <= 1 - SL, the time limit at T; the sell lands LAT later
# (live: 130-180 ms from decision to landing) and is valued on the curve then (our real sell removed from the path).
import json, re, sys
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
LAT = 0.15
TS = [0.5, 0.75, 1.0, 1.3, 1.5, 2.0, 3.0, 4.0]; SLS = [0.05, 0.075, 0.10, 0.125, 0.15, 0.20, None]
def load(name):
    ev = [json.loads(l) for l in open(f"{name}.jsonl")]; real = {}
    for l in open(f"{name}.log.realized"):
        m = re.search(r"mint=(\S+) pnl=([-+0-9.]+)", l)
        if m: real.setdefault(m[1], []).append(float(m[2]))
    sells, tape = {}, {}
    for e in ev:
        if e["ev"] == "sell_land": sells.setdefault(e["mint"], []).append(e)
        if e["ev"] == "tape": tape.setdefault(e["mint"], []).append(e)
    out = []
    for b in (e for e in ev if e["ev"] == "buy_land"):
        m = b["mint"]; s = next((x for x in sells.get(m, []) if x["t"] > b["t"]), None); rl = real.get(m, [])
        if s is None or not rl: continue
        pnl = rl.pop(0)
        tp = sorted((x for x in tape.get(m, []) if b["t"] <= x["t"] <= b["t"] + 6e9 and x["user"] not in US and (x["slot"], x["idx"]) > (b["slot"], b["idx"])), key=lambda x: (x["slot"], x["idx"]))
        tok = b["tokens"]
        pre = [x for x in tp if (x["slot"], x["idx"]) < (s["slot"], s["idx"])]; st = pre[-1] if pre else b
        g0 = st["vsol"] - st["vsol"] * st["vtok"] / (st["vtok"] + tok); fr = 1 - s["sol"] / g0 if g0 > 0 else 0.0125
        def state(x):
            v, k = x["vsol"], x["vtok"]
            if (s["slot"], s["idx"]) < (x["slot"], x["idx"]): v, k = v + g0, k - tok
            return v, k
        def gross(v, k): return v - v * k / (k + tok)
        base = gross(b["vsol"], b["vtok"])
        cover = (max((x["t"] for x in tp), default=b["t"]) - b["t"]) / 1e9
        def value_at(t):
            last = b
            for x in tp:
                if x["t"] <= t: last = x
                else: break
            return gross(*state(last)) if last is not b else base
        res = {}
        for T in TS:
            for SL in SLS:
                tex = b["t"] + T * 1e9
                if SL is not None:
                    for x in tp:
                        if x["t"] > tex: break
                        if gross(*state(x)) / base <= 1 - SL: tex = x["t"]; break
                g = value_at(tex + LAT * 1e9)
                res[(T, SL)] = pnl + (g * (1 - fr) - s["sol"]) / 1e9
        out.append(dict(m=m[:6], real=pnl, cover=cover, res=res))
    return out
for name in sys.argv[1:]:
    rows = load(name); ok = [r for r in rows if r["cover"] >= 3.9] if "ams" not in name else rows
    print(f"\n=== {name}: {len(rows)} fills, real total {sum(r['real'] for r in rows):+.3f} SOL" + ("" if "ams" not in name else "  (Amsterdam tapes stop ~1-1.5 s after the buy: only the 0.5-1.3 s columns are real)"))
    print("time \\ stop-loss " + " ".join(f"{('SL ' + str(int(sl*1000)/10) + '%') if sl else 'no SL':>9}" for sl in SLS))
    for T in TS:
        print(f"  sell at {T:>4}s   " + " ".join(f"{sum(r['res'][(T, sl)] for r in rows):+9.3f}" for sl in SLS))
    best = max(((T, sl) for T in TS for sl in SLS), key=lambda k: sum(r['res'][k] for r in rows))
    print(f"  best: sell at {best[0]} s, SL {best[1]} -> {sum(r['res'][best] for r in rows):+.3f} SOL; current setting -> real {sum(r['real'] for r in rows):+.3f}")

#!/usr/bin/env python3
# Exit-time sweep on live fills (owner 10-24 ~21:50 PKT: "Frankfurt's 4 s hold keeps losing; backrun the losing trades with
# 0.5 s through 4 s, see what the ideal exit point would have been"). For each live fill: the engine's own tape of every trade
# on the token while we held it (vsol/vtok after each trade). A sell at T seconds after our buy landed is valued on the curve
# state at T + 0.05 s (sell landing), with our own sell removed from the path if it happened earlier; pump fee rate calibrated
# on our real sell; buy cost, tx fees and tips as in reality (realized P&L shifted by the difference in sell proceeds).
import json, re, sys, statistics
US = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
TS = [0.5, 1.0, 1.3, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
def run(name):
    ev = [json.loads(l) for l in open(f"{name}.jsonl")]
    real = {}
    for l in open(f"{name}.log.realized"):
        m = re.search(r"mint=(\S+) pnl=([-+0-9.]+)", l)
        if m: real.setdefault(m[1], []).append(float(m[2]))
    buys = [e for e in ev if e["ev"] == "buy_land"]; sells = {}
    for e in ev:
        if e["ev"] == "sell_land": sells.setdefault(e["mint"], []).append(e)
    tape = {}
    for e in ev:
        if e["ev"] == "tape": tape.setdefault(e["mint"], []).append(e)
    rows = []
    for b in buys:
        m = b["mint"]; s = next((x for x in sells.get(m, []) if x["t"] > b["t"]), None)
        rl = real.get(m, []); pnl = rl.pop(0) if rl else None
        if s is None or pnl is None: continue
        tp = sorted((x for x in tape.get(m, []) if b["t"] - 1e9 <= x["t"] <= b["t"] + 6e9 and x["user"] not in US), key=lambda x: (x["slot"], x["idx"]))
        tok = b["tokens"]
        # state right before our real sell -> calibrate the fee rate on our real sell proceeds
        pre = [x for x in tp if (x["slot"], x["idx"]) < (s["slot"], s["idx"])]
        st = pre[-1] if pre else b
        v, k = st["vsol"], st["vtok"]
        gross = v - v * k / (k + tok)
        fr = 1 - s["sol"] / gross if gross > 0 else 0.0125
        out = {}
        for T in TS:
            tt = b["t"] + (T + 0.05) * 1e9
            path = [x for x in tp if (x["slot"], x["idx"]) > (b["slot"], b["idx"]) and x["t"] <= tt]
            stt = path[-1] if path else b
            v, k = stt["vsol"], stt["vtok"]
            if (s["slot"], s["idx"]) < (stt["slot"], stt["idx"]):        # our real sell is inside this path: put the tokens back
                v, k = v + gross, k - tok
            g = v - v * k / (k + tok)
            out[T] = pnl + (g * (1 - fr) - s["sol"]) / 1e9
        last = max((x["t"] for x in tp), default=b["t"])
        rows.append(dict(m=m[:6], size=round(b["sol"] / 1e9, 2), real=pnl, hold=round((s["t"] - b["t"]) / 1e9, 1), cover=round((last - b["t"]) / 1e9, 1), out=out))
    return rows
for name in sys.argv[1:]:
    rows = run(name)
    print(f"\n=== {name}: {len(rows)} fills (P&L in SOL after all costs; columns = sell N seconds after our buy landed)")
    print("token   size  real   held  tape | " + " ".join(f"{t:>6}s" for t in TS) + " | best")
    for r in rows:
        best = max(TS, key=lambda t: r["out"][t])
        print(f"{r['m']} {r['size']:5.2f} {r['real']:+.3f} {r['hold']:4.1f}s {r['cover']:4.1f}s | " + " ".join(f"{r['out'][t]:+.3f}" for t in TS) + f" | {best}s")
    print("TOTAL                         | " + " ".join(f"{sum(r['out'][t] for r in rows):+.3f}" for t in TS) + f" | real {sum(r['real'] for r in rows):+.3f}")
    L = [r for r in rows if r["real"] < 0]
    print(f"LOSERS ({len(L)})                    | " + " ".join(f"{sum(r['out'][t] for r in L):+.3f}" for t in TS) + f" | real {sum(r['real'] for r in L):+.3f}")
    print("won at T                      | " + " ".join(f"{sum(1 for r in rows if r['out'][t] > 0):6d}" for t in TS))

#!/usr/bin/env python3
# WHY DO COPIES LOSE EVEN THOUGH MANY BUYERS COME AFTER THEIR BUY? (read-only, agent tapes). For each first buy of the 3 wallets we fill
# 75 ms later (after every trade within 75 ms). Then: price we pay vs theirs, buy vs sell SOL by others in windows after our fill (sellers
# split into: the wallet itself, the copiers that got in BEFORE us, and everyone else), price path vs our entry, peak and when it happens.
import json, collections, statistics, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
T, F = lib3.load_tapes(); P = json.load(open("out/pos3.json")); W = lib3.W3
def msf(t):
    n = lib3.slot_size(t["s"]) or 450
    return t["s"] * 212.0 + min(t["i"] / max(n, t["i"] + 1), 0.999) * 212.0
px = lambda t: t["vsol"] / t["vtok"]
WIN = [(0, 5), (5, 30), (30, 120), (120, 600)]
rows = []
for p in P:
    tr = T.get(p["m"]); w = W[p["w"]]
    if not tr: continue
    k0 = next((k for k, t in enumerate(tr) if t["user"] == w and t["buy"]), None)
    if k0 is None: continue
    t0 = msf(tr[k0]); their_px = px(tr[k0])
    kf = k0
    while kf + 1 < len(tr) and msf(tr[kf + 1]) - t0 <= 75: kf += 1
    our_px = px(tr[kf]); tf = msf(tr[kf])
    ahead = {t["user"] for t in tr[k0 + 1:kf + 1] if t["buy"] and t["user"] != w}
    ahead_sol = sum(t["sol"] for t in tr[k0 + 1:kf + 1] if t["buy"]) / 1e9
    flows = {}
    for a, b in WIN:
        seg = [t for t in tr[kf + 1:] if a * 1000 < msf(t) - tf <= b * 1000]
        flows[(a, b)] = dict(buy=sum(t["sol"] for t in seg if t["buy"]) / 1e9,
                             sell_w=sum(t["sol"] for t in seg if not t["buy"] and t["user"] == w) / 1e9,
                             sell_ahead=sum(t["sol"] for t in seg if not t["buy"] and t["user"] in ahead) / 1e9,
                             sell_other=sum(t["sol"] for t in seg if not t["buy"] and t["user"] != w and t["user"] not in ahead) / 1e9,
                             buyers=len({t["user"] for t in seg if t["buy"]}))
    path = {}
    for s in (5, 30, 60, 120, 300):
        last = [t for t in tr[kf:] if msf(t) - tf <= s * 1000]
        path[s] = px(last[-1]) / our_px if last else 1.0
    after = tr[kf:]
    peak = max(after, key=px) if after else tr[kf]
    rows.append(dict(w=p["w"], over=our_px / their_px - 1, ahead_n=len(ahead), ahead_sol=ahead_sol, flows=flows, path=path,
                     peak=px(peak) / our_px, t_peak=(msf(peak) - tf) / 1000, their_peak=px(peak) / their_px))
med = lambda v: statistics.median(v) if v else float("nan")
print(f"copies analysed: {len(rows)} (75 ms after their first buy)\n")
for name, sel in (("ALL", rows), ("Fsb6Ns75", [r for r in rows if r["w"] == "Fsb6Ns75"]), ("pXGQ6J2z", [r for r in rows if r["w"] == "pXGQ6J2z"]), ("4vw54BmA", [r for r in rows if r["w"] == "4vw54BmA"])):
    print(f"=== {name} ({len(sel)} copies)")
    print(f"  we pay vs them: median {med([r['over'] for r in sel]):+.0%} | copiers ahead of us: {med([r['ahead_n'] for r in sel]):.0f} wallets, {med([r['ahead_sol'] for r in sel]):.2f} SOL")
    for a, b in WIN:
        f = [r["flows"][(a, b)] for r in sel]
        bs = sum(x["buy"] for x in f); sw = sum(x["sell_w"] for x in f); sa = sum(x["sell_ahead"] for x in f); so = sum(x["sell_other"] for x in f)
        print(f"  {a:3d}-{b:3d} s after our fill: others BUY {bs:7.1f} SOL ({med([x['buyers'] for x in f]):.0f} buyers/token) | SELL {sw + sa + so:7.1f} SOL = wallet itself {sw:6.1f} + copiers who beat us {sa:6.1f} + others {so:6.1f} | net {bs - sw - sa - so:+7.1f}")
    print("  price vs OUR entry: " + " | ".join(f"+{s}s {med([r['path'][s] for r in sel]):.2f}x (up in {sum(r['path'][s] > 1.028 for r in sel) / len(sel):.0%})" for s in (5, 30, 60, 120, 300)))
    print(f"  peak after our fill: median {med([r['peak'] for r in sel]):.2f}x our price, at {med([r['t_peak'] for r in sel]):.1f} s | same peak vs THEIR price {med([r['their_peak'] for r in sel]):.2f}x | round-trip cost ~2.8% (pump fee 1.25% x2 + tx)\n")

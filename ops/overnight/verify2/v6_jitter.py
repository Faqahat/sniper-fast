#!/usr/bin/env python3
"""verify2 / v6: landing-time sensitivity of the corrected replay (repaired tape, absorbed-aware placement, slip, t8).
The claim uses one exact landing time; Run 2 measured 73 and 75 ms on 2 buys. Fills that sit just ahead of a burst the engine
saw a few ms after L flip with a few ms of jitter."""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
SLIP, kinds = V.load_slip(); PRO, SNIPER = V.load_wallet_sets(); ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
CLAIM = {r["m"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
picks = [m for m in P if m in CLAIM]
pre = {}
for m in picks:
    M = V.Mint(m, L[m], X.get(m, []), repair=True, empty_slots=EMPTY)
    seen, miss, how = V.match_anchors(M, V.parse_outs(O[m]["outs"])); ab = V.absorbed_units(M, ENG.get(m), seen)
    pre[m] = (M, seen, ab)
res = {}
for Lm in range(35, 116, 5):
    tot = collections.Counter(); nf = 0
    for m in picks:
        M, seen, ab = pre[m]; ins = V.place2(M, seen, Lm, "opt", ab)
        for var, drop in (("slip", None), ("proafter_slip", PRO)):
            o = V.replay(M, ins, slip=SLIP, drop_buy=drop)
            if o.get("fill") is None: continue
            tot[var] += o["pnl"]
            if var == "slip" and o["fill"]: nf += 1
    res[Lm] = (tot["slip"], tot["proafter_slip"], nf)
    print(f"  L {Lm:3d} ms: slip {tot['slip']:+.3f}  proafter_slip {tot['proafter_slip']:+.3f}  fills {nf}")
for a, b in ((65, 85), (60, 90), (35, 55)):
    ks = [k for k in res if a <= k <= b]
    print(f"  uniform landing {a}-{b} ms: slip {sum(res[k][0] for k in ks) / len(ks):+.3f}  proafter_slip {sum(res[k][1] for k in ks) / len(ks):+.3f}")
# fragility at 75: fills whose next seen anchor arrives within 10 ms after 75
frag = []
for m in picks:
    M, seen, ab = pre[m]; ins = V.place2(M, seen, 75, "opt", ab); o = V.replay(M, ins, slip=SLIP)
    if not o.get("fill"): continue
    nxt = sorted(ms for u, ms in seen.items() if ms >= 75)
    if nxt and nxt[0] < 85: frag.append((m, nxt[0], o["pnl"]))
print(f"  fills at 75 ms with a seen tx arriving within 10 ms after us: {len(frag)}, their PnL {sum(x[2] for x in frag):+.3f}: " + ", ".join(f"{m[:8]} {a:.1f}ms {p:+.3f}" for m, a, p in frag))
json.dump({str(k): v for k, v in res.items()}, open(os.path.join(V.WORK, "v6_jitter.json"), "w"))

#!/usr/bin/env python3
"""BIGLOSS b8: diagnostics of frozen R1 AFTER the one-shot scoring (no re-tuning): VAL ex-attack, by kind, who triggers the
blocks, bootstrap CI, strict-holder robustness (holders bought >= 2 slots before signing), T2/rearm split, hour spread."""
import sys, json, collections, random
B = "/home/moiz/sniper/ops/strategies/presend/bigloss"
sys.path.insert(0, B)
from bscore import *
from brules import *
R = load_feats(); H, HR = hours()
ATT0, ATT1 = 1793590080e9, 1793590680e9  # 11-02 08:28-08:38 PKT attack window (UTC 03:28-03:38)


def blocks_with_reason(R, k=1, X=-0.08, pmin=2.0, s_min=0.3, strict=False):
    _, learn = make_dumper(k, X, pmin, s_min=s_min)
    why = {}
    def rule(r, L):
        if "dump" not in L: return 0.0
        for h in (r.get("holders") or []):
            if h[1] < pmin or h[0] == r["whale"]: continue
            if strict and (h[2] is None or h[2] < 2): continue
            n, net, fl, ws = L["dump"].stats(h[0], r["t_sign"])
            if n >= k and net <= X:
                why[id(r)] = (h[0], round(h[1], 1), n, round(net, 3)); return 1.0
        return 0.0
    res = simulate(R, rule, learn)
    return res, why


res, why = blocks_with_reason(R)
o = report(res, H=H)
print(fmt("R1 (frozen)", o))
noatt = [(r, c) for r, c in res if not (r["rk"] == "r42b" and ATT0 <= r["t_sign"] <= ATT1)]
print(fmt("R1 VAL ex-attack window", report(noatt, sets=("VAL",))))
for k in ("t2", "rearm"):
    print(fmt(f"R1 kind={k}", report([(r, c) for r, c in res if r["kind"] == k], H=H)))
print("\nflagging wallets (HOLD blocks): wallet, n blocked, W, saved")
c = collections.defaultdict(list)
for r, cut in res:
    if cut > 0 and r["set"] == "HOLD": c[why[id(r)][0]].append(r)
for w, rs in sorted(c.items(), key=lambda kv: -len(kv[1]))[:15]:
    print(f"  {w} n {len(rs):3} W {sum(1 for r in rs if r['pnl']>0):3} saved {-sum(r['pnl'] for r in rs):+.3f}")
print("  distinct flagging wallets HOLD:", len(c))
print("  saved w/o the top-3 flagging wallets:", round(sum(-sum(r['pnl'] for r in rs) for w, rs in sorted(c.items(), key=lambda kv: -len(kv[1]))[3:]), 3))
# bootstrap by position within HOLD (blocked set fixed) and by run
random.seed(7)
hb = [-r["pnl"] for r, cut in res if cut > 0 and r["set"] == "HOLD"]
bs = sorted(sum(random.choice(hb) for _ in hb) for _ in range(5000))
print("\nHOLD saved bootstrap (positions) 5/50/95%:", round(bs[250], 3), round(bs[2500], 3), round(bs[4750], 3))
runs = collections.defaultdict(float)
for r, cut in res:
    if cut > 0 and r["set"] == "HOLD": runs[r["rk"]] += -r["pnl"]
rv = list(runs.values()) + [0.0] * (13 - len(runs))
bs2 = sorted(sum(random.choice(rv) for _ in rv) for _ in range(5000))
print("HOLD saved bootstrap (runs) 5/50/95%:", round(bs2[250], 3), round(bs2[2500], 3), round(bs2[4750], 3))
res2, _ = blocks_with_reason(R, strict=True)
print(fmt("\nR1 strict holders (bought >=2 slots before signing)", report(res2, H=H)))
print("\nbig-loss totals: blocked big-loss SOL / all big-loss SOL per split")
for st in ("DEV", "VAL", "HOLD"):
    bl = sum(r["pnl"] for r, cut in res if cut > 0 and r["set"] == st and r["pnl"] <= -0.04)
    al = sum(r["pnl"] for r, cut in res if r["set"] == st and r["pnl"] <= -0.04)
    bw = sum(r["pnl"] for r, cut in res if cut > 0 and r["set"] == st and r["pnl"] > 0.04)
    print(f"  {st}: big losses blocked {bl:.3f} of {al:.3f} | big wins (>0.04) blocked {bw:.3f}")
print("\nr55 blocked positions:")
for r, cut in res:
    if cut > 0 and r["rk"] == "r55": print("  ", r["mint"][:8], r["kind"], round(r["pnl"], 3), why[id(r)])

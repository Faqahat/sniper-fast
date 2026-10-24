#!/usr/bin/env python3
"""verify2 / v8: final comparison table (claim vs mine) at today's and CW-style costs; writes work/v8_final.json"""
import sys, os, json, gzip
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
SLIP, _ = V.load_slip(); PRO, SNIPER = V.load_wallet_sets(); ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
CLAIM = {r["m"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
picks = [m for m in P if m in CLAIM]
COST = dict(today=dict(over=0.02, fail_cost=0.005), cw=dict(over=0.012, fail_cost=0.003))
VARS = dict(slip=None, proafter_slip=PRO, nosnip=SNIPER | PRO)
out = {}
for cfg in ("claim_method", "corrected"):
    for Lm in (75, 45):
        for cname, ck in COST.items():
            for var, drop in VARS.items():
                tot = 0.0; nf = 0
                for m in picks:
                    M = V.Mint(m, L[m], X.get(m, []), repair=(cfg == "corrected"), empty_slots=EMPTY)
                    seen, miss, how = V.match_anchors(M, V.parse_outs(O[m]["outs"]))
                    ab = V.absorbed_units(M, ENG.get(m), seen) if cfg == "corrected" else ()
                    ins = V.place2(M, seen, Lm, "opt", ab)
                    o = V.replay(M, ins, slip=SLIP if var != "nosnip" else None, drop_buy=drop, **ck)
                    if o.get("fill") is None: continue
                    tot += o["pnl"]; nf += bool(o["fill"])
                out[f"{cfg}|{Lm}|{cname}|{var}"] = (round(tot, 3), nf)
for Lm in (75, 45):
    for cname in COST:
        print(f"L{Lm} {cname:5s} " + " | ".join(f"{var}: claim-method {out[f'claim_method|{Lm}|{cname}|{var}'][0]:+.2f} corrected {out[f'corrected|{Lm}|{cname}|{var}'][0]:+.2f}" for var in VARS))
json.dump(out, open(os.path.join(V.WORK, "v8_final.json"), "w"), indent=1)

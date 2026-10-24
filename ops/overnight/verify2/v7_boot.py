#!/usr/bin/env python3
"""verify2 / v7: bootstrap over picks (resample the 235 picks with replacement) of the corrected replay totals."""
import os, json, random
R = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "v3_res.json")))
CL = {r["m"] for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
rows = [r for r in R if r["m"] in CL]
random.seed(7)
out = {}
for key in ("raw|75|opt", "rep|75|abs", "raw|45|opt", "rep|45|abs"):
    for var in ("slip", "proafter_slip", "nosnip"):
        v = [r[key][var].get("pnl", 0.0) for r in rows if r[key][var].get("fill") is not None]
        tots = sorted(sum(random.choice(v) for _ in v) for _ in range(5000))
        p = sum(1 for t in tots if t > 0) / len(tots)
        out[f"{key}|{var}"] = dict(total=round(sum(v), 3), p_pos=round(p, 3), ci90=(round(tots[250], 2), round(tots[4750], 2)))
        print(f"  {key:11s} {var:14s} total {sum(v):+.2f}  P(total>0) {p:.2f}  90% CI [{tots[250]:+.2f}, {tots[4750]:+.2f}]")
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "v7_boot.json"), "w"), indent=1)

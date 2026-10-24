#!/usr/bin/env python3
"""verify2 / a9: the scorer's 'guards' (payer_is_creator, no_bundle_small_dev) were added at 00:18 PKT, 3 minutes after the
VumboDepot rug (an R2 pick at 00:15 PKT), i.e. chosen after seeing an outcome inside the evaluation window. They vetoed 53 later
would-be picks. What would those have made under the same corrected replay?"""
import sys, os, json, gzip
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
VET = json.load(open(os.path.join(V.WORK, "a9_guard_vetoed.json")))
L = V.load_launches(VET); D, O = V.load_scores(VET); X9 = json.load(gzip.open(os.path.join(V.WORK, "x9_txs.json.gz"), "rt"))
SLIP, _ = V.load_slip(); PRO, SNIPER = V.load_wallet_sets()
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
# engine decide lines for these mints
import re
KV = re.compile(r"(\w+)=(\S*)"); ENG = {}; S = set(VET)
for line in open("/home/moiz/sniper-data/collect/shadow/engine_v3.log", errors="replace"):
    if "RACE decide" not in line: continue
    i = line.find("mint="); m = line[i + 5:i + 5 + 50].split()[0]
    if m in S: ENG.setdefault(m, {})["decide"] = dict(KV.findall(line.split(" outs=")[0]))
for Lm in (75, 45):
    tot = {"slip": 0.0, "proafter_slip": 0.0}; nf = 0; n = 0; rows = []
    for m in VET:
        if m not in X9 or m not in O: continue
        M = V.Mint(m, L[m], X9[m], repair=True, empty_slots=EMPTY)
        if M.post_bundle is None: continue
        seen, miss, how = V.match_anchors(M, V.parse_outs(O[m]["outs"])); ab = V.absorbed_units(M, ENG.get(m), seen)
        ins = V.place2(M, seen, Lm, "opt", ab)
        o = V.replay(M, ins, slip=SLIP); o2 = V.replay(M, ins, slip=SLIP, drop_buy=PRO)
        if o.get("fill") is None: continue
        n += 1; tot["slip"] += o["pnl"]; tot["proafter_slip"] += o2["pnl"]; nf += bool(o["fill"])
        if o["fill"]: rows.append((round(o["pnl"], 3), m[:10], L[m].get("name", "")[:18]))
    f = D[VET[0]]["features"]
    print(f"  L{Lm}: guard-vetoed launches replayed {n}, fills {nf}: slip {tot['slip']:+.3f}, proafter_slip {tot['proafter_slip']:+.3f} | fills: {sorted(rows)}")
why = {"payer_is_creator": 0, "no_bundle_small_dev": 0}
for m in VET:
    f = D[m]["features"]
    if f.get("payer_is_creator") != 1: why["payer_is_creator"] += 1
    if (f.get("glued_n") or 0) == 0 and (f.get("dev_buy") or 0) < 1: why["no_bundle_small_dev"] += 1
print("  veto reasons:", why)

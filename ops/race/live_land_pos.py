#!/usr/bin/env python3
# READ-ONLY. Where did OUR live buys land (today's live_land_* / live_bl_exit runs)? Uses live_fires.jsonl (onchain.py):
# our tx position d (non-vote offset after the create) in slot S, or S+k, per send arm, and whether the launch was a race.
import json, re, statistics as st, collections, sys
sys.path.insert(0, "/root/race")
from race_lib import labels
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
pros = frozenset(json.load(open("/root/race/pros.json")))
arm = {}
for f in ["live_land_fast", "live_land_dual", "live_land_staked", "live_land_helius", "live_bl_exit"]:
    for l in open("/root/sniper-fast/%s.log" % f):
        m = re.search(r"FIRE slot=(\d+) mint=(\w+)", l)
        if m:
            arm.setdefault(m.group(2), f)
res = collections.defaultdict(list)
allr = []
for l in open("/root/race/live_fires.jsonl"):
    r = json.loads(l)
    b, s = r["b"], r.get("s") or {}
    if "csig" not in b:
        continue
    o = labels(b, s, pros)
    race = o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3
    mine = [x for x in b["later"] if x["payer"] == ME]
    s1 = [x for x in s.get("rows", []) if x.get("payer") == ME]
    pos = mine[0]["d"] if mine else ("S+%d" % s1[0]["d"] if s1 else "?")
    ahead = sum(1 for d in o["outS_d"] if mine and d < mine[0]["d"])
    res[arm.get(r["mint"], "?")].append(pos)
    allr.append((r["mint"][:8], arm.get(r["mint"], "?"), pos, ahead, race))
for a, v in res.items():
    ins = [x for x in v if isinstance(x, int)]
    print(f"{a:18} n={len(v):2} landed in S {len(ins):2} | median position in S {st.median(ins) if ins else '-'} | {v}")
ins = [x[2] for x in allr if isinstance(x[2], int)]
print(f"\nALL: n={len(allr)} landed in S {len(ins)} ({len(ins) / len(allr):.0%}), median d {st.median(ins)}, d<=25: {sum(1 for d in ins if d <= 25)}")
rc = [x for x in allr if x[4]]
print(f"races (>=3 outside buyers & >=3 SOL in 2 s): {len(rc)} | we landed in S on {sum(1 for x in rc if isinstance(x[2], int))} | positions {[x[2] for x in rc]} | outsiders ahead {[x[3] for x in rc]}")

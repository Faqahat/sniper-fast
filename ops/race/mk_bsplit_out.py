#!/usr/bin/env python3
# READ-ONLY. Write /root/bsplit-format records (mint, slot, dev, glued, gsol, bmult, creator_tip) for the forward run from
# the on-chain cache, split by the engine's gate decision, so the existing /root/bsplit/real_his.py can score them.
# usage: mk_bsplit_out.py <paper.log> <onchain.jsonl> <out_prefix>
import sys, re, json
LOG, OC, PFX = sys.argv[1:4]
fired = {}
for l in open(LOG, errors="replace"):
    m = re.search(r"RACE decide slot=\d+ mint=(\w+) .* pass=(\w+)", l)
    if m:
        fired[m.group(1)] = m.group(2) == "true"
fa, fb = open(PFX + "_fired.jsonl", "w"), open(PFX + "_rejected.jsonl", "w")
n = [0, 0]
for l in open(OC):
    r = json.loads(l)
    b = r.get("b") or {}
    if "csig" not in b or not b.get("base") or r["mint"] not in fired:
        continue
    if any(x.get("ok") and x["ev"] and not x["ev"][-1][4] for x in b.get("later") or []):
        continue
    rec = {"mint": r["mint"], "slot": r["slot"], "dev": b["dev"], "glued": b["glued"], "gsol": b["gsol"] / 1e9,
           "bmult": (b["gv"] / b["base"]) ** 2, "creator_tip": bool(b.get("tips"))}
    (fa if fired[r["mint"]] else fb).write(json.dumps(rec) + "\n")
    n[0 if fired[r["mint"]] else 1] += 1
print("fired", n[0], "rejected", n[1])

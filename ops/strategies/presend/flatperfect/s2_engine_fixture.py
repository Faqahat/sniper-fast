#!/usr/bin/env python3
"""dip36 SKIP-2 per-send parity fixture [read-only]: the parity file's 200 rows (/home/it/sniper-data/skip2/parity_persend_r55.jsonl) each
joined with its presend_live_arm record from the r55 log (by mint, w), so the engine test checks the arm-record inputs (1-34) from the
real records and the score from x_filled. -> tests/fixtures/fpnb/skip2_parity_r55.jsonl (one line per row: the parity row + "arm")
usage: s2_engine_fixture.py OUT.jsonl"""
import json, sys

D = "/home/it/sniper-data/skip2"
rows = [json.loads(l) for l in open(f"{D}/parity_persend_r55.jsonl")]
want = {(r["mint"], r["w"]) for r in rows}
arms = {}
for raw in open(f"{D}/dip_ams_r55.jsonl", "rb"):
    if b'"ev":"presend_live_arm"' not in raw: continue
    d = json.loads(raw)
    tr = d.get("trig") or d.get("dump") or {}
    k = (d.get("mint") or tr.get("mint"), d.get("w"))
    if k in want: arms[k] = d
with open(sys.argv[1], "w") as f:
    n = 0
    for r in rows:
        a = arms.get((r["mint"], r["w"]))
        if a is None: continue
        r["arm"] = a; f.write(json.dumps(r) + "\n"); n += 1
print("rows", len(rows), "with arm", n)

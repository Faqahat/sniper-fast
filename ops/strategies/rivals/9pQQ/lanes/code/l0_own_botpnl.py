#!/usr/bin/env python3
"""LANES step 0a: every tx signed by 9pQQ from botpnl9 pass-1 files (4 runs), raw JSON lines kept -> lanes/own_raw_<run>.jsonl"""
import json, glob, os
W = "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"
IN = "/home/moiz/sniper-data/botpnl9"; OUT = "/home/moiz/sniper-data/rivals/9pQQ/lanes"
for r in ["run_20261028_1405", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]:
    n = 0; seen = set()
    with open(f"{OUT}/own_raw_{r}.jsonl", "w") as fo:
        for fn in sorted(glob.glob(f"{IN}/{r}/p1_*.jsonl")):
            for l in open(fn, errors="replace"):
                if W not in l: continue
                d = json.loads(l)
                if (d.get("signers") or [None])[0] != W or d["sig"] in seen: continue
                seen.add(d["sig"]); fo.write(l if l.endswith("\n") else l + "\n"); n += 1
    print(r, n, flush=True)

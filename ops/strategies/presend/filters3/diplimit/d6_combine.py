#!/usr/bin/env python3
"""DIPLIMIT step 6: combine replay chunks into one table (e.g. r42 covered part = c1..c7; c7 = after the 11-01 12:00 PKT DEV/VAL cut).
usage: d6_combine.py LABEL TAG [TAG ...]"""
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/diplimit")
from d4_score import table
D = "/home/moiz/sniper-data/filters3/diplimit"
label, tags = sys.argv[1], sys.argv[2:]
rows = []; hours = 0
for t in tags:
    r = json.load(open(f"{D}/replay_{t}.json"))["rows"]; rows += r
    ts = sorted(x["t"] for x in r); hours += (ts[-1] - ts[0]) / 3.6e12
o = table(rows, hours, label)
json.dump({"hours": hours, "table": o}, open(f"{D}/combined_{label}.json", "w"), indent=1)

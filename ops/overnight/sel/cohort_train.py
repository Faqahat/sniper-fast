#!/usr/bin/env python3
# Profitable-bot cohort from TRAIN hours only (no look at the test hours): census rows (one per wallet x token) of launches
# before SPLIT; same rule as census/rank.py "consistent winners": >= 30 tokens, total > 0, both halves > 0, >= 3 of 4 quarters > 0.
# -> sel/cohort_train.json (full addresses). Local only.
import json, gzip, glob, collections, time, calendar, os
SPLIT = calendar.timegm(time.strptime("2026-" + os.environ.get("SPLIT", "10-23 06:00"), "%Y-%m-%d %H:%M")) - 18000
A = collections.defaultdict(list)
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        if r[3] < SPLIT: A[r[0]].append(r)
cons = []
for u, v in A.items():
    if len(v) < 30: continue
    v.sort(key=lambda r: r[3]); pn = [r[11] for r in v]; h = len(v) // 2
    q = [sum(pn[i * len(v) // 4:(i + 1) * len(v) // 4]) for i in range(4)]
    if sum(pn) > 0 and sum(pn[:h]) > 0 and sum(pn[h:]) > 0 and sum(1 for x in q if x > 0) >= 3: cons.append(u)
old = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_cw.json")))
json.dump(sorted(cons), open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json", "w"))
print(f"wallets with rows before the split: {len(A)}; consistent winners (train only): {len(cons)}; overlap with the old 541 list: {len(old & set(cons))}")

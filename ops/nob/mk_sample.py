#!/usr/bin/env python3
# Build a uniform random sample of successful creates from csigs.jsonl (mint authority sigs).
# usage: mk_sample.py <n> <seed> <out.json> [exclude.json ...]
import sys, json, random
n, seed, outp = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
excl = set()
for f in sys.argv[4:]:
    for t in json.load(open(f)):
        excl.add(t.get("sig"))
xs = []
seen = set()
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l)
    if x["err"] or x["signature"] in seen:
        continue
    seen.add(x["signature"])
    xs.append(x)
xs.sort(key=lambda x: x["slot"])
random.seed(seed)
pool = [x for x in xs if x["signature"] not in excl]
pick = random.sample(pool, n)
json.dump([{"slot": x["slot"], "sig": x["signature"], "tag": "rand"} for x in pick], open(outp, "w"))
print("population", len(xs), "picked", len(pick))

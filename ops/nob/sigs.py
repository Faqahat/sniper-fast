#!/usr/bin/env python3
# READ-ONLY. Page getSignaturesForAddress for one address from newest back to the ledger start (or min_slot).
# Resumable: appends to out.jsonl, continues from the oldest sig already written.
# usage: sigs.py <address> <out.jsonl> [min_slot]
import sys, json, os, time
sys.path.insert(0, "/root/indep")
from common import rpc

ADDR, OUT = sys.argv[1], sys.argv[2]
MIN_SLOT = int(sys.argv[3]) if len(sys.argv) > 3 else 0
before = None
n = 0
if os.path.exists(OUT):
    last = None
    for l in open(OUT):
        try:
            last = json.loads(l)
            n += 1
        except Exception:
            pass
    if last:
        before = last["signature"]
        print("resume from", last["slot"], "n", n, flush=True)
out = open(OUT, "a")
empty = 0
while True:
    prm = {"limit": 1000}
    if before:
        prm["before"] = before
    r = rpc("getSignaturesForAddress", [ADDR, prm], tries=8)
    if not isinstance(r, list):
        print("ERR", str(r)[:200], flush=True)
        time.sleep(3)
        empty += 1
        if empty > 5:
            break
        continue
    if not r:
        break
    for x in r:
        out.write(json.dumps({"signature": x["signature"], "slot": x["slot"], "err": x.get("err") is not None,
                              "bt": x.get("blockTime")}) + "\n")
    out.flush()
    n += len(r)
    before = r[-1]["signature"]
    print(time.strftime("%H:%M:%S"), "n", n, "oldest slot", r[-1]["slot"], flush=True)
    if r[-1]["slot"] < MIN_SLOT:
        break
print("FINISHED", n, flush=True)

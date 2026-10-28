#!/usr/bin/env python3
"""8yYMhu step 2 (read-only, public RPC getTransaction jsonParsed, maxSupportedTransactionVersion 1, finalized).
Reads every DATA/want_*.txt ("sig why" per line, processed in file-name order), skips sigs already fetched, appends to DATA/gettx.jsonl.
Resumable; safe to re-run while new want files are added (it re-scans the want files when its queue empties)."""
import json, os, sys, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc
D = "/home/moiz/sniper-data/rivals/8yYMhu"
fn = f"{D}/gettx.jsonl"
done = set()
if os.path.exists(fn):
    for l in open(fn):
        try: j = json.loads(l)
        except Exception: continue
        if j.get("res") is not None: done.add(j["sig"])
f = open(fn, "a"); n = 0; t0 = time.time()
while True:
    want = []
    for w in sorted(glob.glob(f"{D}/want_*.txt")):
        for l in open(w):
            p = l.split()
            if p and p[0] not in done: want.append((p[0], p[1] if len(p) > 1 else os.path.basename(w)))
    seen = set(); want = [x for x in want if not (x[0] in seen or seen.add(x[0]))]
    if not want: break
    print(f"queue {len(want)} done {len(done)}", flush=True)
    for sig, why in want:
        j = rpc.call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "finalized"}])
        f.write(json.dumps({"sig": sig, "why": why, "res": j.get("result"), "err": j.get("error")}) + "\n"); f.flush(); n += 1
        if j.get("result") is not None: done.add(sig)
        else: print("NULL", sig[:16], str(j.get("error"))[:120], flush=True); done.add(sig)
        if n % 50 == 0: print(f"{n} fetched, {n / (time.time() - t0):.2f}/s", flush=True)
print("ALLDONE", n, flush=True)

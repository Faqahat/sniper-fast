#!/usr/bin/env python3
# READ-ONLY RPC: fetch given tx signatures (raw getTransaction JSON) -> raw/<name>.jsonl.gz (resumable)
# usage: python3 -I f1b_sigs.py NAME sigs.json   (sigs.json = list of signatures or of [.., .., sig, ..] rows with the sig at index 2)
import sys, os, json, time, gzip, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
NAME = sys.argv[1]; S = json.load(open(sys.argv[2])); S = [s if isinstance(s, str) else s[2] for s in S]
OUT = f"raw/{NAME}.jsonl.gz"
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
have = set()
if os.path.exists(OUT):
    try:
        for l in gzip.open(OUT, "rt"):
            try: have.add(json.loads(l)["sig"])
            except Exception: pass
    except (EOFError, OSError): pass
todo = list(dict.fromkeys(s for s in S if s not in have))
print(NAME, "todo", len(todo), flush=True)
def one(s): return s, rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
n = 0
with gzip.open(OUT, "at") as fo, cf.ThreadPoolExecutor(8) as ex:
    for s, t in ex.map(one, todo):
        if t: t["sig"] = s; fo.write(json.dumps(t, separators=(",", ":")) + "\n"); n += 1
print("done", n, flush=True)

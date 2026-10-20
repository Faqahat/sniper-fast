# READ-ONLY. For every tape launch: re-read the create tx and find the LARGEST non-signer SOL transfer (what the engine's
# --race-create-tip-prefix checks) vs "any Lunar tip". Output: mint -> largest dest label/prefix, amount, any_moon.
# usage: python3 tipsplit.py <tapes.jsonl> <out.json>
import sys, json
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc, b58dec, load_tipmap
TM = load_tipmap()
SYS = "11111111111111111111111111111111"
rows = [json.loads(l) for l in open(sys.argv[1])]


def work(r):
    t = rpc("getTransaction", [r["csig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not isinstance(t, dict) or "transaction" not in t: return r["mint"], None
    msg = t["transaction"]["message"]; meta = t["meta"]
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]; signers = set(keys[:nsig])
    xf = []
    ixs = list(msg["instructions"])   # TOP-LEVEL only, like the engine (inner = pump moving the dev buy into the curve)
    for ix in ixs:
        if keys[ix["programIdIndex"]] != SYS: continue
        d = b58dec(ix["data"])
        if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
            dst = keys[ix["accounts"][1]]
            if dst not in signers: xf.append((int.from_bytes(d[4:12], "little"), dst))
    if not xf: return r["mint"], dict(largest="none", amt=0, any_moon=False)
    amt, dst = max(xf)
    return r["mint"], dict(largest=("moon" if dst.startswith("moon") else TM.get(dst, "other:" + dst[:8])), amt=amt / 1e9,
                           any_moon=any(d.startswith("moon") for _, d in xf), n=len(xf))


with ThreadPoolExecutor(6) as ex:
    out = dict(ex.map(work, rows))
json.dump(out, open(sys.argv[2], "w"))
import collections
print("largest-transfer destination:", collections.Counter((v or {}).get("largest", "?").split(":")[0] for v in out.values()).most_common(10))
print("any moon & largest=moon:", sum(1 for v in out.values() if v and v["any_moon"] and v["largest"] == "moon"),
      " any moon & largest NOT moon:", sum(1 for v in out.values() if v and v["any_moon"] and v["largest"] != "moon"))

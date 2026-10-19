#!/usr/bin/env python3
# READ-ONLY: what do CPI creates (outer program) look like at top level? + flag mismatch details + failed-create errors.
import sys, json, collections as C
sys.path.insert(0, "/root/det")
from dlib import *
R = [json.loads(l) for l in open(sys.argv[1])]
cpi = [r for r in R if r.get("top") is False and not r.get("err")]
for r in cpi[:3]:
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    print("CPI", r["mint"][:10], "signers", [k[:8] for k in keys[:nsig]], "nstatic", len(msg["accountKeys"]), "true_dev", r["true_dev"], "quote", (r.get("ev") or {}).get("quote_mint", "")[:6])
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]
        d = b58dec(ix["data"])
        print("   top", p[:8], "nacc", len(ix["accounts"]), "data", len(d), d[:8].hex(), "accs", [keys[i][:6] for i in ix["accounts"]][:20])
    print("   logs", [l[:70] for l in t["meta"]["logMessages"] if "Instruction:" in l][:8])
ev = [r for r in R if r.get("ev") and r.get("kind") == "create_v2" and not r.get("err")]
for r in ev:
    a, e = r["args"], r["ev"]
    if a.get("holder") != e.get("holder") or a.get("fee_bps") != e.get("fee_bps"):
        print("FLAGMISMATCH", r["mint"][:10], "trailing", a.get("trailing"), "args", {k: a[k] for k in ("mayhem", "cashback", "fee_bps", "holder")}, "ev", {k: e.get(k) for k in ("mayhem", "cashback", "fee_bps", "holder")})
fails = [r for r in R if r.get("err")]
errs = C.Counter()
for r in fails[:25]:
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if isinstance(t, dict) and t.get("meta"):
        e = t["meta"].get("err")
        logs = [l for l in t["meta"]["logMessages"] if "Error" in l or "error" in l or "failed" in l]
        errs[(json.dumps(e)[:60], (logs[-1][:90] if logs else ""))] += 1
for k, v in errs.most_common(10):
    print("FAILED", v, k)

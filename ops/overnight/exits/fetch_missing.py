#!/usr/bin/env python3
# READ-ONLY: re-fetch the few txs the saved ledgers marked "missing" (public RPC, slow, backoff) and convert them to ledger
# records (same format as ledger.py). Output: cache/ledger_<w>_missing.json
import sys, os, json, time, urllib.request, urllib.error
EX = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, EX)
from common import WALLETS, LEDGER, decode_events
PUB = "https://api.mainnet-beta.solana.com"
def get(sig):
    for i in range(8):
        try:
            req = urllib.request.Request(PUB, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}]}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=60))
            if r.get("result"): return r["result"]
            time.sleep(3 * (i + 1))
        except urllib.error.HTTPError as e: time.sleep(10 * (i + 1) if e.code == 429 else 3)
        except Exception: time.sleep(3)
    return None
for w, W in WALLETS.items():
    D = json.load(open(f"{LEDGER}/ledger_{w}.json")); out = []
    for x in [x for x in D["txs"] if x.get("missing")]:
        t = get(x["sig"]); time.sleep(2.5)
        if not t: print(w, x["sig"][:12], "still missing", flush=True); continue
        json.dump(t, open(os.path.join(EX, "cache", f"txc_{w}", x["sig"] + ".json"), "w"))
        m = t["transaction"]["message"]; meta = t["meta"]; keys = [k["pubkey"] for k in m["accountKeys"]]
        i = keys.index(W) if W in keys else None
        sol_chg = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else 0.0
        tok = {}
        pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in meta.get("postTokenBalances") or []}
        for ai in set(pre) | set(post):
            b = post.get(ai) or pre.get(ai)
            if b.get("owner") != W: continue
            a0 = float(((pre.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0); a1 = float(((post.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0)
            if a1 != a0: tok[b["mint"]] = tok.get(b["mint"], 0) + a1 - a0
        trades = [dict(mint=e["mint"], sol=e["sol"] / 1e9, buy=e["buy"]) for e in decode_events(t) if e["user"] == W]
        xfers = []
        for ix in list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]:
            pp = ix.get("parsed")
            if isinstance(pp, dict) and pp.get("type") in ("transfer", "transferWithSeed", "transferChecked") and isinstance(pp.get("info"), dict) and "lamports" in pp["info"]:
                inf = pp["info"]
                if inf.get("source") == W or inf.get("destination") == W: xfers.append((inf.get("source"), inf.get("destination"), inf["lamports"] / 1e9))
        out.append(dict(sig=x["sig"], slot=t["slot"], bt=t.get("blockTime"), err=meta.get("err") is not None, fee=meta["fee"] / 1e9, sol_chg=sol_chg, tok=tok, trades=trades, xfers=xfers,
                        signer=keys[0], progs=sorted({keys[ix["programIdIndex"]] if "programIdIndex" in ix else ix.get("programId") for ix in m["instructions"]})))
        print(w, x["sig"][:12], "ok", trades, flush=True)
    json.dump(dict(wallet=W, txs=out), open(os.path.join(EX, "cache", f"ledger_{w}_missing.json"), "w"))
print("DONE", flush=True)

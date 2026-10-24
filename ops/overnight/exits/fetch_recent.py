#!/usr/bin/env python3
# READ-ONLY: extend a wallet ledger with the txs AFTER the saved ledger (CK RPC, <= 8 req/s), same record format as
# ops/snipers/ledger/ledger.py, raw txs cached into cache/txc_<w>/.  Output: cache/ledger_<w>_recent.json
import sys, os, json, concurrent.futures as cf
EX = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, EX)
from rpc import rpc, get_tx
from common import WALLETS, LEDGER, decode_events
w = sys.argv[1]; W = WALLETS[w]
D = json.load(open(f"{LEDGER}/ledger_{w}.json"))
last = max((x for x in D["txs"] if x.get("slot")), key=lambda x: x["slot"])
sigs = []; before = None
while True:
    p = {"limit": 1000, "until": last["sig"]}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p])
    if not r: break
    sigs += r; before = r[-1]["signature"]
    if len(r) < 1000: break
known = {x["sig"] for x in D["txs"]}
sigs = [s for s in sigs if s["signature"] not in known]
print(w, "new signatures after ledger end", len(sigs), flush=True)
OUT = os.path.join(EX, "cache", f"txc_{w}"); os.makedirs(OUT, exist_ok=True)
def one(s):
    p = os.path.join(OUT, s["signature"] + ".json")
    t = json.load(open(p)) if os.path.exists(p) else get_tx(s["signature"])
    if not t: return dict(sig=s["signature"], slot=s["slot"], bt=s.get("blockTime"), missing=True)
    if not os.path.exists(p): json.dump(t, open(p, "w"))
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
    return dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), err=meta.get("err") is not None, fee=meta["fee"] / 1e9, sol_chg=sol_chg, tok=tok, trades=trades, xfers=xfers,
                signer=keys[0], progs=sorted({keys[ix["programIdIndex"]] if "programIdIndex" in ix else ix.get("programId") for ix in m["instructions"]}))
with cf.ThreadPoolExecutor(6) as ex: L = list(ex.map(one, sigs))
bal = (rpc("getBalance", [W]) or {}).get("value", 0) / 1e9
json.dump(dict(wallet=W, balance_now=bal, holdings_now=[], txs=L, after_sig=last["sig"]), open(os.path.join(EX, "cache", f"ledger_{w}_recent.json"), "w"))
print(w, "saved", len(L), "txs;", sum(1 for x in L if x.get("missing")), "missing;", sum(1 for x in L if x.get("trades")), "with trades", flush=True)

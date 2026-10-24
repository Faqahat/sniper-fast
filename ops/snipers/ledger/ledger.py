#!/usr/bin/env python3
# READ-ONLY full ledger of a wallet since its first transaction: every tx (failed ones too) with the wallet's SOL change,
# token-balance changes of the token accounts it owns, its pump.fun trades, system transfers in/out with counterparties.
# Signatures from public mainnet-beta (full history), transactions from RPC_URL (owner's, fast).
# usage: RPC_URL=... python3 -I ledger.py <wallet> <out.json>
import sys, os, json, time, base64, urllib.request, concurrent.futures as cf
W, OUT = sys.argv[1], sys.argv[2]; EP = os.environ["RPC_URL"]; PUB = "https://api.mainnet-beta.solana.com"
def rpc(m, p, ep=None, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep or EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1 + i)
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
sigs, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p], ep=PUB)
    if not r: break
    sigs += r; before = r[-1]["signature"]; time.sleep(0.5)
    if len(r) < 1000: break
print(f"{W}: {len(sigs)} signatures all-time ({sum(1 for s in sigs if s.get('err') is not None)} failed)", flush=True)
def one(s):
    t = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    if not t: t = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=PUB)
    if not t: return dict(sig=s["signature"], slot=s["slot"], bt=s.get("blockTime"), missing=True)
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
    trades = []
    for l in meta.get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        x = l[14:].strip(); x += "=" * (-len(x) % 4)
        try: raw = base64.b64decode(x)
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 129 and b58(raw[57:89]) == W:
            trades.append(dict(mint=b58(raw[8:40]), sol=int.from_bytes(raw[40:48], "little") / 1e9, buy=raw[56] == 1))
    xfers = []
    for ix in list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]:
        p = ix.get("parsed")
        if isinstance(p, dict) and p.get("type") in ("transfer", "transferWithSeed", "transferChecked") and isinstance(p.get("info"), dict) and "lamports" in p["info"]:
            inf = p["info"]
            if inf.get("source") == W or inf.get("destination") == W: xfers.append((inf.get("source"), inf.get("destination"), inf["lamports"] / 1e9))
    return dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), err=meta.get("err") is not None, fee=meta["fee"] / 1e9, sol_chg=sol_chg, tok=tok, trades=trades, xfers=xfers,
                signer=keys[0], progs=sorted({keys[ix["programIdIndex"]] if "programIdIndex" in ix else ix.get("programId") for ix in m["instructions"]}))
with cf.ThreadPoolExecutor(10) as ex: L = list(ex.map(one, sigs))
bal = rpc("getBalance", [W])["value"] / 1e9
toks = rpc("getTokenAccountsByOwner", [W, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}, {"encoding": "jsonParsed"}]) or {"value": []}
toks2 = rpc("getTokenAccountsByOwner", [W, {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}, {"encoding": "jsonParsed"}]) or {"value": []}
hold = [(a["account"]["data"]["parsed"]["info"]["mint"], a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]) for a in toks["value"] + toks2["value"]]
json.dump(dict(wallet=W, balance_now=bal, holdings_now=[h for h in hold if h[1]], txs=L), open(OUT, "w"))
print(f"saved {len(L)} txs ({sum(1 for x in L if x.get('missing'))} missing); balance now {bal:.4f} SOL; token accounts with balance {sum(1 for h in hold if h[1])}", flush=True)

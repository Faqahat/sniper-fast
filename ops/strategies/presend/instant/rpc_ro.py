#!/usr/bin/env python3
# Read-only RPC helper (owner's endpoint, read from ~/.config/sniper/ck_rpc_url, NEVER printed). Paced to <= 4 calls/s, answers
# cached on disk (never asked twice). getTransaction / getBlock / getSignaturesForAddress only.
import os, json, time, urllib.request, threading, hashlib
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
CACHE_DIR = "/home/moiz/sniper-data/presend_instant/rpc_cache"; os.makedirs(CACHE_DIR, exist_ok=True)
_lk = threading.Lock(); _last = [0.0]; _n = [0]
def rpc(m, p, tries=5):
    key = hashlib.sha1(json.dumps([m, p], sort_keys=True).encode()).hexdigest()
    f = f"{CACHE_DIR}/{key}.json"
    if os.path.exists(f): return json.load(open(f))
    for i in range(tries):
        with _lk:
            w = _last[0] + 0.25 - time.time()
            if w > 0: time.sleep(w)
            _last[0] = time.time(); _n[0] += 1
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=90))
            if "result" in r:
                json.dump(r["result"], open(f, "w")); return r["result"]
            if "error" in r and r["error"].get("code") in (-32007, -32009, -32004): return None
        except Exception: pass
        time.sleep(0.8 * (i + 1))
    return None
def calls(): return _n[0]
def tx(sig): return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
def block(slot): return rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "full", "maxSupportedTransactionVersion": 0, "rewards": False, "commitment": "confirmed"}])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
SHORT = {SYS: "System", CB: "CB", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ATA",
         "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token22",
         "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95": "Lighthouse", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ": "pumpfees",
         "Vote111111111111111111111111111111111111111": "Vote"}
def anatomy(t):
    """structure of one tx from getTransaction / a getBlock entry (json encoding)"""
    if not t: return None
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    ixs = []; nonce = False; cup = cul = None; tips = []
    for k, ix in enumerate(msg["instructions"]):
        p = keys[ix["programIdIndex"]]; d = b58dec(ix["data"]) if ix.get("data") else b""
        nm = SHORT.get(p, p[:8])
        if p == SYS and len(d) >= 4:
            code = int.from_bytes(d[:4], "little")
            if code == 4: nonce = nonce or k == 0; nm = "AdvanceNonce"
            elif code == 2 and len(d) >= 12:
                to = keys[ix["accounts"][1]]
                if to in TIP or to.startswith("noz"): tips.append((TIP.get(to, "nozomi"), int.from_bytes(d[4:12], "little"), k)); nm = "Tip:" + TIP.get(to, "nozomi")
                else: nm = "Transfer"
        if p == CB and d:
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cul = int.from_bytes(d[1:5], "little")
        ixs.append(nm)
    ver = t.get("version", "legacy")
    return dict(version=ver, nsig=msg["header"]["numRequiredSignatures"], signers=msg["accountKeys"][:msg["header"]["numRequiredSignatures"]], ixs=ixs, nonce=nonce,
                cup=cup, cul=cul, tips=tips, alts=len(msg.get("addressTableLookups") or []), fee=meta.get("fee"), cu=meta.get("computeUnitsConsumed"),
                err=meta.get("err"), nkeys=len(keys), slot=t.get("slot"), blockhash=msg.get("recentBlockhash"))

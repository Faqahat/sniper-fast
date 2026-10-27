#!/usr/bin/env python3
# competitors2/txshape.py -- READ-ONLY. Fetch raw transactions (getTransaction, base64) from the PUBLIC mainnet RPC and decode
# their shape: size in bytes, legacy / v0, address lookup tables, durable nonce (AdvanceNonceAccount first), the top-level
# instruction list (program + kind), compute-budget values, tip transfers (relay via tipmap), signer count, recent blockhash.
# usage: python3 -I txshape.py sigs.txt   (one signature per line; cached in /home/moiz/sniper-data/competitors2/txshape.jsonl)
import json, sys, os, time, base64, urllib.request, urllib.error
URLS = os.environ.get("PUB_RPC", "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com").split(",")
_rr = [0]
CACHE = "/home/moiz/sniper-data/competitors2/txshape.jsonl"
TIP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
NAMES = {SYS: "system", CB: "computebudget", PUMP: "pump", ATA: "ata", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "token",
         "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "token2022", "L2TExMFKdjpN9kozasaurPtRJ3kjGcVM1LJbxBb2ErSN": "lighthouse",
         "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "memo", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo": "memo1",
         "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpamm", "ComputeBudget": "computebudget"}

def cu16(b, o):
    v = 0; s = 0
    while True:
        x = b[o]; o += 1; v |= (x & 0x7f) << s; s += 7
        if not x & 0x80: return v, o

def decode(raw):
    o = 0; nsig, o = cu16(raw, o); o += 64 * nsig
    ver = "legacy"
    if raw[o] & 0x80: ver = f"v{raw[o] & 0x7f}"; o += 1
    hdr = list(raw[o:o + 3]); o += 3
    nk, o = cu16(raw, o); keys = [b58enc(raw[o + 32 * j:o + 32 * (j + 1)]) for j in range(nk)]; o += 32 * nk
    bh = b58enc(raw[o:o + 32]); o += 32
    ni, o = cu16(raw, o); ixs = []
    for _ in range(ni):
        p = raw[o]; o += 1
        na, o = cu16(raw, o); acc = list(raw[o:o + na]); o += na
        nd, o = cu16(raw, o); data = raw[o:o + nd]; o += nd
        ixs.append((p, acc, data))
    alts = []
    if ver != "legacy":
        nl, o = cu16(raw, o)
        for _ in range(nl):
            k = b58enc(raw[o:o + 32]); o += 32
            nw, o = cu16(raw, o); o += nw
            nr, o = cu16(raw, o); o += nr
            alts.append([k, nw, nr])
    return dict(nsig=nsig, ver=ver, hdr=hdr, keys=keys, bh=bh, ixs=ixs, alts=alts)

def shape(sig, res):
    raw = base64.b64decode(res["transaction"][0]); d = decode(raw); meta = res.get("meta") or {}
    la = meta.get("loadedAddresses") or {}; allk = d["keys"] + la.get("writable", []) + la.get("readonly", [])
    ixl = []; cb = {}; tips = []; nonce = False
    for j, (p, acc, data) in enumerate(d["ixs"]):
        prog = allk[p] if p < len(allk) else f"?{p}"; nm = NAMES.get(prog, prog[:8])
        kind = ""
        if prog == SYS and len(data) >= 4:
            code = int.from_bytes(data[:4], "little")
            kind = {0: "create", 2: "transfer", 3: "createWithSeed", 4: "advanceNonce", 8: "allocate"}.get(code, str(code))
            if code == 4 and j == 0: nonce = True
            if code == 2 and len(data) >= 12 and len(acc) >= 2:
                to = allk[acc[1]]; lam = int.from_bytes(data[4:12], "little")
                tips.append([TIP.get(to, "?" + to[:6]), lam])
        elif prog == CB and data:
            c = data[0]; kind = {0: "requestUnits", 1: "heapFrame", 2: "cuLimit", 3: "cuPrice", 4: "loadedDataLimit"}.get(c, str(c))
            if c == 2: cb["cul"] = int.from_bytes(data[1:5], "little")
            elif c == 3: cb["cup"] = int.from_bytes(data[1:9], "little")
            elif c == 4: cb["ldl"] = int.from_bytes(data[1:5], "little")
            elif c == 1: cb["heap"] = int.from_bytes(data[1:5], "little")
        elif data:
            kind = data[:8].hex() if len(data) >= 8 else data.hex()
        ixl.append(f"{nm}:{kind}" if kind else nm)
    return dict(sig=sig, slot=res.get("slot"), size=len(raw), ver=d["ver"], nsig=d["nsig"], nkeys=len(d["keys"]),
                nalt=len(d["alts"]), alt_keys=sum(a[1] + a[2] for a in d["alts"]), alts=[a[0] for a in d["alts"]],
                nonce=nonce, nonce_acct=(allk[d["ixs"][0][1][0]] if nonce else None), bh=d["bh"], ixs=ixl, cb=cb, tips=tips,
                signers=d["keys"][:d["nsig"]], err=meta.get("err"), fee=meta.get("fee"), cu=meta.get("computeUnitsConsumed"), cost=meta.get("costUnits"),
                bt=res.get("blockTime"),
                logs_tail=(meta.get("logMessages") or [])[-3:])


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b

def shape_json(sig, res, size):
    tx = res["transaction"]; m = tx["message"]; meta = res.get("meta") or {}
    la = meta.get("loadedAddresses") or {}; keys = m["accountKeys"]; allk = keys + la.get("writable", []) + la.get("readonly", [])
    ixl = []; cb = {}; tips = []; nonce = False; nacct = None
    for j, ix in enumerate(m["instructions"]):
        prog = allk[ix["programIdIndex"]]; nm = NAMES.get(prog, prog[:8]); data = b58dec(ix["data"]); acc = ix["accounts"]; kind = ""
        if prog == SYS and len(data) >= 4:
            code = int.from_bytes(data[:4], "little")
            kind = {0: "create", 2: "transfer", 3: "createWithSeed", 4: "advanceNonce", 8: "allocate"}.get(code, str(code))
            if code == 4 and j == 0: nonce = True; nacct = allk[acc[0]]
            if code == 2 and len(data) >= 12 and len(acc) >= 2:
                to = allk[acc[1]]; tips.append([TIP.get(to, "?" + to[:6]), int.from_bytes(data[4:12], "little")])
        elif prog == CB and data:
            c = data[0]; kind = {0: "requestUnits", 1: "heapFrame", 2: "cuLimit", 3: "cuPrice", 4: "loadedDataLimit"}.get(c, str(c))
            if c == 2: cb["cul"] = int.from_bytes(data[1:5], "little")
            elif c == 3: cb["cup"] = int.from_bytes(data[1:9], "little")
            elif c == 4: cb["ldl"] = int.from_bytes(data[1:5], "little")
            elif c == 1: cb["heap"] = int.from_bytes(data[1:5], "little")
        elif data:
            kind = data[:8].hex() if len(data) >= 8 else data.hex()
        ixl.append(f"{nm}:{kind}" if kind else nm)
    tc = m.get("transactionConfig")
    if tc: cb["v1config"] = tc
    nsig = m["header"]["numRequiredSignatures"]
    return dict(sig=sig, slot=res.get("slot"), size=size, ver=("v%s" % res.get("version")) if res.get("version") not in (None, "legacy") else "legacy",
                nsig=nsig, nkeys=len(keys), nalt=len(m.get("addressTableLookups") or []),
                alt_keys=sum(len(a["writableIndexes"]) + len(a["readonlyIndexes"]) for a in (m.get("addressTableLookups") or [])),
                alts=[a["accountKey"] for a in (m.get("addressTableLookups") or [])], nonce=nonce, nonce_acct=nacct, bh=m["recentBlockhash"],
                ixs=ixl, cb=cb, tips=tips, signers=keys[:nsig], err=meta.get("err"), fee=meta.get("fee"), cu=meta.get("computeUnitsConsumed"),
                cost=meta.get("costUnits"), bt=res.get("blockTime"), nwritable=nsig - m["header"]["numReadonlySignedAccounts"] + (len(keys) - nsig - m["header"]["numReadonlyUnsignedAccounts"]) + len(la.get("writable", [])),
                logs_tail=(meta.get("logMessages") or [])[-2:])

def fetch2(sig):
    a = fetch(sig, "json")
    if not a: return None, None
    b = fetch(sig, "base64")
    size = len(base64.b64decode(b["transaction"][0])) if b else None
    return a, size

def fetch(sig, enc="base64"):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                       "params": [sig, {"encoding": enc, "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}]}).encode()
    for k in range(8):
        URL = URLS[_rr[0] % len(URLS)]; _rr[0] += 1
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"content-type": "application/json", "user-agent": "curl/8.5.0"}), timeout=15))
            if r.get("result"): return r["result"]
            if r.get("error"): time.sleep(0.5 + k); continue
            return None
        except urllib.error.HTTPError as e:
            time.sleep(1 + k if e.code == 429 else 0.5)
        except Exception:
            time.sleep(0.5)
    return None

if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    done = set()
    if os.path.exists(CACHE):
        for l in open(CACHE):
            try:
                o = json.loads(l)
                if not o.get("missing"): done.add(o["sig"])
            except Exception: pass
    sigs = list(dict.fromkeys(s.strip() for s in open(sys.argv[1]) if s.strip() and s.strip() not in done))
    print(f"to fetch {len(sigs)} (cached {len(done)})", flush=True)
    nth = int(os.environ.get("THREADS", "4")); ok = 0
    def one(s):
        res, size = fetch2(s)
        if not res: return dict(sig=s, missing=True)
        try: return shape_json(s, res, size)
        except Exception as e: return dict(sig=s, decode_error=str(e)[:200])
    with open(CACHE, "a") as out, ThreadPoolExecutor(nth) as ex:
        for n, o in enumerate(ex.map(one, sigs), 1):
            out.write(json.dumps(o) + "\n"); out.flush(); ok += "size" in o
            if n % 50 == 0: print(f"{n}/{len(sigs)} ok {ok}", flush=True)
    print("done ok", ok, flush=True)

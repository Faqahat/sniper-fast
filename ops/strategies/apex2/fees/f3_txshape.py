#!/usr/bin/env python3
"""APEX-FEES step 3: tx shape of sampled rival txs via public RPC getTransaction (read-only, <= 2 req/s).
Durable nonce = first instruction is System AdvanceNonceAccount (u32 LE 4). Also: version, #ix, CU limit/price ix, LUT use, size.
usage: f3_txshape.py IN.json OUT.json   (IN: {wallet: [sig, ...]})"""
import sys, json, time, base64, urllib.request

U = "https://api.mainnet-beta.solana.com"
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(A58)}
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"

def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b

def rpc(m, p):
    d = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for k in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(U, data=d, headers={"content-type": "application/json"}), timeout=30))
            if "error" in r: time.sleep(2 + 2 * k); continue
            return r.get("result")
        except Exception:
            time.sleep(2 + 2 * k)
    return None

def shape(t):
    tx = t["transaction"]; msg = tx["message"]; keys = msg["accountKeys"]
    la = (t.get("meta") or {}).get("loadedAddresses") or {}
    allk = keys + la.get("writable", []) + la.get("readonly", [])
    ixs = msg["instructions"]; progs = [allk[ix["programIdIndex"]] for ix in ixs]
    nonce = False
    if ixs and progs[0] == SYS:
        d = b58dec(ixs[0]["data"]); nonce = d[:4] == b"\x04\0\0\0"
    cul = cup = None
    for ix, p in zip(ixs, progs):
        if p == CB:
            d = b58dec(ix["data"])
            if d[:1] == b"\x02": cul = int.from_bytes(d[1:5], "little")
            elif d[:1] == b"\x03": cup = int.from_bytes(d[1:9], "little")
    return dict(slot=t["slot"], version=t.get("version"), nonce=nonce, nix=len(ixs), progs=progs, cul=cul, cup=cup,
                luts=len(msg.get("addressTableLookups") or []), nkeys=len(keys), nsig=len(tx["signatures"]),
                err=(t.get("meta") or {}).get("err") is not None, fee=(t.get("meta") or {}).get("fee"))

if __name__ == "__main__":
    IN = json.load(open(sys.argv[1])); out = {}
    for w, sigs in IN.items():
        out[w] = []
        for s in sigs:
            t = rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            time.sleep(0.6)
            if t: x = shape(t); x["sig"] = s; out[w].append(x)
        n = len(out[w]); print(w[:8], n, "nonce", sum(x["nonce"] for x in out[w]), flush=True)
        json.dump(out, open(sys.argv[2], "w"))

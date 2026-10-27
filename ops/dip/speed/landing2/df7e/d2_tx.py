#!/usr/bin/env python3
# DF7eRXHn study: read-only tx anatomy via getTransaction (rpc_ro, cached, <= 4 req/s). Prints one block per sig.
# usage: python3 -I d2_tx.py SIG [SIG ...]   (or -j to print json summary lines)
import sys, json, base64, os
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
from rpc_ro import get_tx, rpc
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
NAMES = {SYS: "System", CB: "ComputeBudget", PUMP: "pump", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token2022",
         "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ATA",
         "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95": "Lighthouse", "41Pr4XqEcmgV1PqZF9yccpuFvxF7PpKLGfTD9jWJBn1q": "own41Pr4X",
         "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ": "pumpFees", "ComputeBudget111111111111111111111111111111": "ComputeBudget"}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
SZ = "/home/moiz/sniper-data/landing2/txcache_size.json"
SIZES = json.load(open(SZ)) if os.path.exists(SZ) else {}
def size(sig):
    if sig in SIZES: return SIZES[sig]
    t = rpc("getTransaction", [sig, {"encoding": "base64", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    n = len(base64.b64decode(t["transaction"][0])) if t else None
    SIZES[sig] = n; json.dump(SIZES, open(SZ, "w")); return n
def anat(sig):
    t = get_tx(sig)
    if not t: return None
    tx = t["transaction"]; m = tx["message"]; meta = t["meta"]
    keys = list(m["accountKeys"]) + (meta.get("loadedAddresses") or {}).get("writable", []) + (meta.get("loadedAddresses") or {}).get("readonly", [])
    out = dict(sig=sig, slot=t["slot"], ver=t.get("version"), nkeys=len(m["accountKeys"]), alt=bool(m.get("addressTableLookups")),
               err=meta.get("err"), fee=meta["fee"], cu=meta.get("computeUnitsConsumed"), size=size(sig), ixs=[], tips=[], nonce=None)
    for k, ix in enumerate(m["instructions"]):
        p = keys[ix["programIdIndex"]]; d = dec(ix["data"]); acc = [keys[a] for a in ix["accounts"]]
        nm = NAMES.get(p, p[:8]); desc = nm
        if p == CB:
            if d[0] == 2: desc = f"CU limit {int.from_bytes(d[1:5], 'little')}"
            elif d[0] == 3: desc = f"CU price {int.from_bytes(d[1:9], 'little')}"
            elif d[0] == 4: desc = f"loaded-data limit {int.from_bytes(d[1:5], 'little')}"
        elif p == SYS:
            it = int.from_bytes(d[:4], "little")
            if it == 4: desc = "AdvanceNonce"; out["nonce"] = acc[0]
            elif it == 2:
                lam = int.from_bytes(d[4:12], "little"); sv = lib2.svc_of(acc[1]) or lib2.UNK.get(acc[1]) or acc[1][:8]
                desc = f"Transfer {lam/1e9:.6f} -> {sv}"
                if lib2.svc_of(acc[1]) or acc[1] in lib2.UNK: out["tips"].append((sv, lam, k))
            elif it == 3: desc = f"CreateAccountWithSeed space={int.from_bytes(d[-48:-40], 'little') if len(d)>=52 else '?'}"
            else: desc = f"System#{it}"
        elif nm == "own41Pr4X": desc = f"own41Pr4X data={d[:1].hex()}..{len(d)}B accts={len(acc)}"
        elif nm == "pump": desc = f"pump disc={d[:8].hex()} {len(d)}B"
        elif nm.startswith("Token"): desc = f"{nm} ix#{d[0] if d else '-'}"
        out["ixs"].append(desc)
    out["logs_tail"] = [l for l in (meta.get("logMessages") or []) if "Error" in l or "failed" in l or "Program log: " in l][:6]
    return out
if __name__ == "__main__":
    js = "-j" in sys.argv
    for s in [a for a in sys.argv[1:] if a != "-j"]:
        a = anat(s)
        if js: print(json.dumps(a)); continue
        if not a: print(s[:12], "not found"); continue
        print(f"== {s[:16]} slot {a['slot']} v={a['ver']} size={a['size']}B keys={a['nkeys']} alt={a['alt']} fee={a['fee']} cu={a['cu']} err={a['err']} nonce={a['nonce']}")
        for k, d in enumerate(a["ixs"]): print(f"   {k}: {d}")
        for l in a["logs_tail"]: print("   log:", l[:150])

"""Decode a getTransaction (json encoding) of a 9pQQ tx into a flat feature dict."""
import struct
A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; AI = {c: k for k, c in enumerate(A)}
def b58d(s):
    n = 0
    for c in s: n = n * 58 + AI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; CB = "ComputeBudget111111111111111111111111111111"; SYS = "11111111111111111111111111111111"
def dec(tx):
    m = tx["transaction"]["message"]; keys = m["accountKeys"]; meta = tx["meta"]
    out = dict(slot=tx["slot"], ver=tx.get("version"), nkeys=len(keys), alt=len(m.get("addressTableLookups") or []), bh=m["recentBlockhash"],
               nix=len(m["instructions"]), sig_n=m["header"]["numRequiredSignatures"], ro_uns=m["header"]["numReadonlyUnsignedAccounts"])
    seq = []; cb = []
    for ix in m["instructions"]:
        p = keys[ix["programIdIndex"]]; data = b58d(ix["data"])
        if p == CB:
            t = data[0]
            if t == 2: cb.append(("lim", struct.unpack_from("<I", data, 1)[0])); seq.append("CUlim")
            elif t == 3: cb.append(("price", struct.unpack_from("<Q", data, 1)[0])); seq.append("CUprice")
            elif t == 4: cb.append(("ldsz", struct.unpack_from("<I", data, 1)[0])); seq.append("LDsz")
            else: seq.append(f"CB{t}")
        elif p == SYS:
            if data[:4] == b"\x02\0\0\0":
                lam = struct.unpack_from("<Q", data, 4)[0]; to = keys[ix["accounts"][1]]
                seq.append(f"T:{to[:5]}"); out.setdefault("tips", []).append((to[:8], lam))
            elif data[:4] == b"\x04\0\0\0": seq.append("NonceAdv"); out["nonce"] = 1
            else: seq.append("SYS?")
        elif p == PUMP:
            out["pdisc"] = data[:8].hex(); out["plen"] = len(data); out["pargs"] = [struct.unpack_from("<Q", data, 8 + 8 * k)[0] for k in range((len(data) - 8) // 8)]
            out["ptail"] = data[8 + 8 * ((len(data) - 8) // 8):].hex(); out["pacc"] = len(ix["accounts"]); out["pacc_ix"] = ix["accounts"]
            seq.append("PUMP")
        elif p.startswith("ATokenGP"): seq.append("ATA" + (data.hex() or "0"))
        else: seq.append(p[:6])
    out["seq"] = "|".join(seq); out["cb"] = cb
    out["cu"] = meta.get("computeUnitsConsumed"); out["fee"] = meta.get("fee"); out["err"] = meta.get("err")
    out["nlog"] = None
    out["size_est"] = sum(len(b58d(ix["data"])) + len(ix["accounts"]) for ix in m["instructions"]) + 32 * len(keys)
    return out

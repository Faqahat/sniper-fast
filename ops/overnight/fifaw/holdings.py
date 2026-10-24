#!/usr/bin/env python3
# READ-ONLY: the wallet's balances now (SOL + every token account), with the bonding-curve state of pump tokens it still holds
import sys, os, json, base64, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
W = rpcu.W; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big"); return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
# PDA derivation (ed25519 off-curve check)
P = 2 ** 255 - 19; Dc = -121665 * pow(121666, P - 2, P) % P
def on_curve(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= P: return False
    u = (y * y - 1) % P; v = (Dc * y * y + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    if x2 == 0: return True
    return pow(x2, (P - 1) // 2, P) == 1
def pda(seeds, prog):
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + b58d(prog) + b"ProgramDerivedAddress").digest()
        if not on_curve(h): return b58e(h)
bal = rpcu.rpc("getBalance", [W])["value"] / 1e9
acc = []
for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    r = rpcu.rpc("getTokenAccountsByOwner", [W, {"programId": prog}, {"encoding": "jsonParsed"}])
    for a in r["value"]:
        inf = a["account"]["data"]["parsed"]["info"]
        acc.append(dict(acct=a["pubkey"], mint=inf["mint"], ui=inf["tokenAmount"]["uiAmount"] or 0.0, raw=int(inf["tokenAmount"]["amount"]), dec=inf["tokenAmount"]["decimals"], lamports=a["account"]["lamports"], prog=prog[:5]))
for a in acc:
    if a["ui"] and a["mint"].endswith("pump"):
        bc = pda([b"bonding-curve", b58d(a["mint"])], PUMP)
        v = rpcu.rpc("getAccountInfo", [bc, {"encoding": "base64"}])["value"]
        if v:
            d = base64.b64decode(v["data"][0]); vtok = int.from_bytes(d[8:16], "little"); vsol = int.from_bytes(d[16:24], "little"); complete = d[48] == 1 if len(d) > 48 else None
            a["curve"] = dict(vsol=vsol, vtok=vtok, complete=complete, px_sol_per_tok=(vsol / vtok) if vtok else None)
            a["value_sol_curve"] = a["raw"] * vsol / (vtok + a["raw"]) / 1e9 if vtok else 0.0     # sell-all value on the curve (before fees)
json.dump(dict(balance=bal, accounts=acc), open("holdings_now.json", "w"), indent=1)
print("SOL", bal, "| token accounts", len(acc), "| with balance", sum(1 for a in acc if a["ui"]), "| rent locked", round(sum(a["lamports"] for a in acc) / 1e9, 4))
for a in sorted(acc, key=lambda a: -a["ui"]):
    if a["ui"]: print(a["mint"], a["ui"], a.get("value_sol_curve"), a.get("curve", {}).get("complete"))

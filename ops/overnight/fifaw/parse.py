#!/usr/bin/env python3
# READ-ONLY, offline: parse every cached tx of the wallet (txc_FiFawH) into one ledger row each -> ledger_FiFawH.json
# value accounting: SOL change of the wallet + WSOL + stables (USDC/USDT/USD1 at SOLUSD) ; token deltas for accounts it owns.
import sys, os, json, base64, collections, re
HERE = os.path.dirname(os.path.abspath(__file__))
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
TIPS = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
WSOL = "So11111111111111111111111111111111111111112"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
STABLE = {USDC, "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"}
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; CB = "ComputeBudget111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big"); return b"\0" * (len(s) - len(s.lstrip("1"))) + b
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
def tiplabel(d):
    if d in TIPS: return TIPS[d]
    if d.startswith(("noz", "TEMPa")): return "nozomi"
    if d.lower().startswith("astra"): return "astralane"
    return None
VEN = {PUMP: "pump", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap", "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "launchlab",
       "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "clmm", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "dlmm", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "whirlpool",
       "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "cpmm", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "amm4", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "jupiter"}
def parse(t):
    m = t["transaction"]["message"]; meta = t["meta"]; sig = t["transaction"]["signatures"][0]
    keys = [k["pubkey"] for k in m["accountKeys"]]; signers = [k["pubkey"] for k in m["accountKeys"] if k.get("signer")]
    i = keys.index(W) if W in keys else None
    sol_chg = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else 0.0
    tok = collections.defaultdict(float); tok_raw = {}
    pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in meta.get("postTokenBalances") or []}
    for ai in set(pre) | set(post):
        b = post.get(ai) or pre.get(ai)
        if b.get("owner") != W: continue
        a0 = float(((pre.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0); a1 = float(((post.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0)
        if a1 != a0: tok[b["mint"]] += a1 - a0
    ixs = m["instructions"]; inner = [ix for g in (meta.get("innerInstructions") or []) for ix in g["instructions"]]
    top = [ix.get("programId") for ix in ixs]; allp = set(top) | {ix.get("programId") for ix in inner}
    cu_price = cu_limit = lds = None; cb_extra = []; nonce = None; tips = []; xin = []; xout = []
    for ix in ixs:
        pid = ix.get("programId"); p = ix.get("parsed")
        if pid == CB:
            d = b58d(ix.get("data", ""))
            if d[:1] == b"\x03": cu_price = int.from_bytes(d[1:9], "little")
            elif d[:1] == b"\x02": cu_limit = int.from_bytes(d[1:5], "little")
            elif d[:1] == b"\x04": lds = int.from_bytes(d[1:5], "little")
            if ix.get("accounts"): cb_extra += ix["accounts"]
        if isinstance(p, dict) and p.get("type") == "advanceNonce": nonce = p["info"]["nonceAccount"]
    for ix in ixs + inner:
        p = ix.get("parsed")
        if isinstance(p, dict) and p.get("type") in ("transfer", "transferWithSeed", "createAccount", "createAccountWithSeed") and isinstance(p.get("info"), dict) and "lamports" in p["info"]:
            inf = p["info"]; src = inf.get("source"); dst = inf.get("destination") or inf.get("newAccount"); lam = inf["lamports"]
            if src == W and ix in ixs and p.get("type") == "transfer" and tiplabel(dst): tips.append((tiplabel(dst), lam, dst))
            elif src == W and p.get("type") == "transfer": xout.append((dst, lam))
            elif dst == W: xin.append((src, lam))
    ev = []; logs = meta.get("logMessages") or []
    for l in logs:
        if not l.startswith("Program data: "): continue
        x = l[14:].strip(); x += "=" * (-len(x) % 4)
        try: raw = base64.b64decode(x)
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 129:
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            ev.append(dict(mint=b58e(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58e(raw[57:89]), ts=u(89), vsol=u(97), vtok=u(105)))
    ixnames = [l.split("Instruction: ", 1)[1].strip() for l in logs if "Program log: Instruction: " in l]
    err = meta.get("err"); errinfo = None
    if err:
        msg = next((l for l in logs if "Error Code:" in l or "Error Message" in l), None)
        fail = next((l for l in logs if " failed: " in l), None)
        errinfo = dict(raw=err, code=(re.search(r"Error Code: (\w+)", msg).group(1) if msg and re.search(r"Error Code: (\w+)", msg) else None), failed=fail[:160] if fail else None,
                       last=[l[:160] for l in logs[-4:]])
    return dict(sig=sig, slot=t["slot"], bt=t.get("blockTime"), v=t.get("version"), signer=signers[0] if signers else None, nsig=len(signers), err=err is not None, errinfo=errinfo,
                fee=meta["fee"], cu=meta.get("computeUnitsConsumed"), cu_price=cu_price, cu_limit=cu_limit, lds=lds, cb_extra=cb_extra, nonce=nonce, bh=m.get("recentBlockhash"),
                top=top, venues=sorted({VEN[p] for p in allp if p in VEN}), routers=[p for p in top if p and p not in VEN and p not in (CB, "11111111111111111111111111111111", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")],
                ixnames=ixnames, sol_chg=sol_chg, tok=dict(tok), tips=tips, xin=xin, xout=xout, ev=[e for e in ev if e["user"] == W], ev_all=len(ev),
                ntop=len(ixs), w_in=i is not None)
if __name__ == "__main__":
    S = json.load(open(os.path.join(HERE, "sigs_FiFawH.json"))); C = os.path.join(HERE, "txc_FiFawH")
    L = []
    for s in S:
        f = os.path.join(C, s["signature"] + ".json")
        if not os.path.exists(f): continue
        L.append(parse(json.load(open(f))))
    L.sort(key=lambda x: (x["slot"], x["sig"]))
    json.dump(L, open(os.path.join(HERE, "ledger_FiFawH.json"), "w"))
    print("parsed", len(L), "| signer==W", sum(1 for x in L if x["signer"] == W), "| other signers", collections.Counter(x["signer"][:8] for x in L if x["signer"] != W).most_common(10))

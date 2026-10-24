#!/usr/bin/env python3
# READ-ONLY, offline: every cached tx of the wallet (txc/<sig>.json) -> one compact row (rows.json):
# SOL / token deltas, fee, CU, version, nonce account, tips (by landing service, from tipmap.json), other transfers
# (counterparties), pump TradeEvents of the wallet (exact curve state), instruction names, error + failing program.
import sys, os, json, glob, base64, collections
HERE = os.path.dirname(os.path.abspath(__file__))
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
WSOL = "So11111111111111111111111111111111111111112"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
TIP.update({"3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT": "jito"})
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
NAMES = {"11111111111111111111111111111111": "system", "ComputeBudget111111111111111111111111111111": "cb", PUMP: "pump",
         "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "token22",
         "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "token", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ata",
         "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "whirlpool", "ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8": "ENFJAV",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "jupiter", "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "launchlab",
         "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "raydium_clmm", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "meteora_dlmm",
         "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "raydium_cpmm", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium_amm",
         "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "memo", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ": "pump_fees"}
def trade(raw):
    o = 8; mint = b58e(raw[o:o + 32]); o += 32
    sol = int.from_bytes(raw[o:o + 8], "little"); o += 8; tok = int.from_bytes(raw[o:o + 8], "little"); o += 8
    isbuy = raw[o]; o += 1; user = b58e(raw[o:o + 32]); o += 32; ts = int.from_bytes(raw[o:o + 8], "little"); o += 8
    vsol = int.from_bytes(raw[o:o + 8], "little"); o += 8; vtok = int.from_bytes(raw[o:o + 8], "little"); o += 8
    rsol = int.from_bytes(raw[o:o + 8], "little"); o += 8; rtok = int.from_bytes(raw[o:o + 8], "little"); o += 8
    d = dict(mint=mint, sol=sol, tok=tok, buy=isbuy == 1, user=user, ts=ts, vsol=vsol, vtok=vtok)
    if len(raw) >= o + 32 + 8 + 8 + 32 + 8 + 8:
        o += 32; d["fbps"] = int.from_bytes(raw[o:o + 8], "little"); o += 8; d["fee"] = int.from_bytes(raw[o:o + 8], "little"); o += 8
        d["creator"] = b58e(raw[o:o + 32]); o += 32; d["cbps"] = int.from_bytes(raw[o:o + 8], "little"); o += 8; d["cfee"] = int.from_bytes(raw[o:o + 8], "little"); o += 8
    return d
def one(t, sig):
    m = t["transaction"]["message"]; meta = t["meta"]; keys = [k["pubkey"] for k in m["accountKeys"]]
    signers = [k["pubkey"] for k in m["accountKeys"] if k.get("signer")]
    i = keys.index(W) if W in keys else None
    sol_chg = (meta["postBalances"][i] - meta["preBalances"][i]) if i is not None else 0
    tok = collections.defaultdict(float); tokraw = collections.defaultdict(int)
    pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in meta.get("postTokenBalances") or []}
    for ai in set(pre) | set(post):
        b = post.get(ai) or pre.get(ai)
        if b.get("owner") != W: continue
        a0 = int(((pre.get(ai) or {}).get("uiTokenAmount") or {}).get("amount") or 0); a1 = int(((post.get(ai) or {}).get("uiTokenAmount") or {}).get("amount") or 0)
        dec = int((b.get("uiTokenAmount") or {}).get("decimals") or 0)
        if a1 != a0: tok[b["mint"]] += (a1 - a0) / 10 ** dec; tokraw[b["mint"]] += a1 - a0
    tops = [ix.get("programId") for ix in m["instructions"]]
    inner = [ix.get("programId") for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]
    allix = list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]
    nonce = None; tips = []; xo = []; xi = []; seedacc = 0; closes = 0; ata_create = 0; cbl = None; cbp = None
    for k, ix in enumerate(m["instructions"]):
        p = ix.get("parsed")
        pid = ix.get("programId")
        if isinstance(p, dict) and p.get("type") == "advanceNonce": nonce = p["info"]["nonceAccount"]
        if pid == "ComputeBudget111111111111111111111111111111":
            raw = b58d(ix.get("data") or "")
            if raw[:1] == b"\x02": cbl = int.from_bytes(raw[1:5], "little")
            if raw[:1] == b"\x03": cbp = int.from_bytes(raw[1:9], "little")
        if pid == "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": ata_create += 1
    for ix in allix:
        p = ix.get("parsed")
        if not isinstance(p, dict): continue
        inf = p.get("info") if isinstance(p.get("info"), dict) else {}
        ty = p.get("type")
        if ty == "createAccountWithSeed" and inf.get("source") == W: seedacc += 1
        if ty == "closeAccount": closes += 1
        if ty in ("transfer", "transferWithSeed") and "lamports" in inf:
            s, d, l = inf.get("source"), inf.get("destination"), inf["lamports"]
            if s == W and d in TIP: tips.append((TIP[d], l, d))
            elif s == W: xo.append((d, l))
            elif d == W: xi.append((s, l))
    # top-level SPL token transfers signed by the wallet to an account it does not own (payments / withdrawals in tokens)
    owners = {}; decs = {}
    for b in (meta.get("preTokenBalances") or []) + (meta.get("postTokenBalances") or []):
        owners[keys[b["accountIndex"]]] = (b.get("owner"), b.get("mint")); decs[b.get("mint")] = (b.get("uiTokenAmount") or {}).get("decimals")
    ttx = []
    for ix in m["instructions"]:
        p_ = ix.get("parsed")
        if not isinstance(p_, dict) or p_.get("type") not in ("transfer", "transferChecked"): continue
        inf = p_.get("info") or {}
        if "lamports" in inf: continue
        if inf.get("authority") != W and inf.get("multisigAuthority") != W: continue
        own, mint = owners.get(inf.get("destination"), (None, inf.get("mint")))
        if own == W or own is None: continue      # own accounts, incl. temp accounts created + closed inside the tx (WSOL unwrap)
        amt = (inf.get("tokenAmount") or {}).get("uiAmount")
        if amt is None and "amount" in inf:
            mt = mint or owners.get(inf.get("source"), (None, None))[1]
            dec = decs.get(mt)
            amt = int(inf["amount"]) / 10 ** (dec if dec is not None else 6)
        ttx.append((own, mint or (owners.get(inf.get("source"), (None, None))[1]), amt))
    trades = []; ixn = []
    for l in meta.get("logMessages") or []:
        if l.startswith("Program log: Instruction: "): ixn.append(l[26:].strip())
        if not l.startswith("Program data: "): continue
        x = l[14:].strip(); x += "=" * (-len(x) % 4)
        try: raw = base64.b64decode(x)
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 129:
            tr = trade(raw)
            if tr["user"] == W: trades.append(tr)
    err = meta.get("err"); efail = None
    if err:
        # failing program + its error text from the logs
        lg = meta.get("logMessages") or []
        for l in lg:
            if " failed: " in l: efail = l[:200]
        for l in lg:
            if "Error Code:" in l or "Error Message:" in l or "slippage" in l.lower() or "Error" in l and "AnchorError" in l: efail = (efail or "") + " | " + l[:200]
    rb = m.get("recentBlockhash")
    jdf = any(k.startswith("jitodontfront") for k in keys)
    return dict(sig=sig, slot=t["slot"], bt=t.get("blockTime"), v=t.get("version"), err=json.dumps(err) if err else None, efail=efail,
                fee=meta["fee"], cu=meta.get("computeUnitsConsumed"), nsig=len(t["transaction"]["signatures"]), signers=signers,
                payer=keys[0], nonce=nonce, bh=rb, tops=[NAMES.get(p, p) for p in tops], inner=sorted({NAMES.get(p, p) for p in inner}),
                tips=tips, xo=xo, xi=xi, jdf=jdf, seedacc=seedacc, closes=closes, ata=ata_create, cbl=cbl, cbp=cbp,
                sol_chg=sol_chg, ttx=ttx, tok=dict(tok), tokraw=dict(tokraw), trades=trades, ixn=ixn, nkeys=len(keys),
                router_data=[ix.get("data") for ix in m["instructions"] if ix.get("programId") not in NAMES or NAMES.get(ix.get("programId")) in ("ENFJAV", "pump")])
if __name__ == "__main__":
    sigs = json.load(open(os.path.join(HERE, "sigs.json")))
    rows = []; miss = 0
    for s in sigs:
        f = os.path.join(HERE, "txc", s["signature"] + ".json")
        if not os.path.exists(f): miss += 1; continue
        rows.append(one(json.load(open(f)), s["signature"]))
    rows.sort(key=lambda r: (r["slot"], r["sig"]))
    # a few txs come back with blockTime 0: interpolate from the nearest txs by slot
    good = [(r["slot"], r["bt"]) for r in rows if r["bt"]]
    import bisect
    gs = [g[0] for g in good]
    for r in rows:
        if not r["bt"] and good:
            i = min(max(bisect.bisect_left(gs, r["slot"]), 1), len(good) - 1); (s0, b0), (s1, b1) = good[i - 1], good[i]
            r["bt"] = int(b0 + (r["slot"] - s0) * ((b1 - b0) / (s1 - s0) if s1 != s0 else 0.214)); r["bt_interp"] = True
    json.dump(rows, open(os.path.join(HERE, "rows.json"), "w"))
    print(f"rows {len(rows)} (not cached yet {miss})")

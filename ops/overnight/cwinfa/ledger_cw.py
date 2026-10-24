#!/usr/bin/env python3
# READ-ONLY, offline: parse every cached CWiNFA transaction (txc/<sig>.json, jsonParsed) into a ledger row:
#   SOL change of the wallet, fee, version, durable nonce, compute budget (limit / price), CU used, tips (labelled with
#   tipmap.json), router (5DVzy5Ep...) instruction decoded (tag, amount, min-out, seed / key, flags), pump.fun instruction
#   (name + args), TradeEvents of the wallet (mint, SOL, tokens, fees, reserves), token balance changes of its accounts,
#   system transfers in/out with counterparties, error (code + name from the logs).
# usage: python3 -I ledger_cw.py  -> ledger_CWiNFA.json
import os, sys, json, base64, hashlib, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from rpcw import b58dec, b58enc, W
TIPS = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
def tiplabel(a):
    if a in TIPS: return TIPS[a]
    if a.startswith(("noz", "TEMPa")): return "nozomi"
    if a.lower().startswith("astra"): return "astralane"
    return None
ROUTER = "5DVzy5EpG2xVxrwwuyZPDe9EpraUnGh7ZgYABwizzNVu"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; CB = "ComputeBudget111111111111111111111111111111"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
PIX = {hashlib.sha256(("global:" + n).encode()).digest()[:8]: n for n in
       ("buy", "sell", "buy_exact_sol_in", "buy_exact_quote_in", "buy_exact_quote_in_v3", "buy_v3", "sell_v3", "buy_v2", "sell_v2", "create", "create_v2")}
u64 = lambda b, o: int.from_bytes(b[o:o + 8], "little")
def events(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != TD or len(raw) < 225: continue
        out.append(dict(mint=b58enc(raw[8:40]), sol=u64(raw, 40), tok=u64(raw, 48), buy=raw[56] == 1, user=b58enc(raw[57:89]), ts=int.from_bytes(raw[89:97], "little", signed=True),
                        vsol=u64(raw, 97), vtok=u64(raw, 105), fee=u64(raw, 169), cfee=u64(raw, 217), creator=b58enc(raw[177:209])))
    return out
def one(sig):
    t = json.load(open(os.path.join(HERE, "txc", sig + ".json")))
    m = t["transaction"]["message"]; meta = t["meta"]; logs = meta.get("logMessages") or []
    keys = [k["pubkey"] for k in m["accountKeys"]]
    i = keys.index(W) if W in keys else None
    sol_chg = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else 0.0
    pre_bal = meta["preBalances"][i] / 1e9 if i is not None else None; post_bal = meta["postBalances"][i] / 1e9 if i is not None else None
    tok = {}
    pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in meta.get("postTokenBalances") or []}
    for ai in set(pre) | set(post):
        b = post.get(ai) or pre.get(ai)
        if b.get("owner") != W: continue
        a0 = int(((pre.get(ai) or {}).get("uiTokenAmount") or {}).get("amount") or 0); a1 = int(((post.get(ai) or {}).get("uiTokenAmount") or {}).get("amount") or 0)
        dec = ((post.get(ai) or pre.get(ai)).get("uiTokenAmount") or {}).get("decimals", 6)
        if a1 != a0: tok[b["mint"]] = tok.get(b["mint"], 0) + (a1 - a0) / 10 ** dec
    nonce = None; cul = cup = None; tips = []; xfers = []; router = None; pump_ix = None; progs = []; nclose = 0
    allix = [(None, ix) for ix in m["instructions"]] + [(inn["index"], ix) for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]
    for top, ix in allix:
        pid = ix.get("programId"); p = ix.get("parsed")
        if top is None: progs.append(pid)
        if isinstance(p, dict):
            ty = p.get("type"); inf = p.get("info") or {}
            if ty == "advanceNonce" and top is None: nonce = inf.get("nonceAccount")
            if ty in ("transfer", "transferWithSeed") and "lamports" in inf and (inf.get("source") == W or inf.get("destination") == W):
                lab = tiplabel(inf.get("destination", "")) if inf.get("source") == W else None
                if lab and top is None: tips.append([lab, inf["lamports"] / 1e9, inf["destination"]])
                else: xfers.append([inf.get("source"), inf.get("destination"), inf["lamports"] / 1e9, top is None])
            if ty == "closeAccount": nclose += 1
            continue
        if pid == CB and top is None:
            d = b58dec(ix["data"])
            if d[:1] == b"\x02": cul = int.from_bytes(d[1:5], "little")
            if d[:1] == b"\x03": cup = int.from_bytes(d[1:9], "little")
        if pid == ROUTER and top is None:
            d = b58dec(ix["data"])
            if d and d[0] == 2 and len(d) >= 25: router = dict(tag=2, amount=u64(d, 1), min_out=u64(d, 9), seed=d[17:25].decode("latin1"))
            elif d and d[0] == 3 and len(d) >= 49: router = dict(tag=3, amount=u64(d, 1), min_out=u64(d, 9), key=b58enc(d[17:49]), flags=d[49:].hex())
            else: router = dict(tag=d[0] if d else None, hex=d.hex()[:120])
        if pid == PUMP and top is not None and len(ix.get("accounts") or []) > 3:
            d = b58dec(ix["data"]); nm = PIX.get(d[:8], d[:8].hex())
            pump_ix = dict(name=nm, a1=u64(d, 8) if len(d) >= 16 else None, a2=u64(d, 16) if len(d) >= 24 else None, n=len(d))
    err = meta.get("err"); errname = None; errcode = None
    if err:
        for l in logs:
            if "Error Code: " in l: errname = l.split("Error Code: ")[1].split(".")[0]
            if "Error Number: " in l: errcode = l.split("Error Number: ")[1].split(".")[0]
        if not errname:
            ie = err.get("InstructionError") if isinstance(err, dict) else None
            errname = json.dumps(ie if ie else err)[:80]
    ev = [e for e in events(logs) if e["user"] == W]
    names = [l.split("Instruction: ")[1] for l in logs if "Instruction: " in l]
    return dict(sig=sig, slot=t["slot"], bt=t.get("blockTime"), v=t.get("version"), err=bool(err), errname=errname, errcode=errcode, fee=meta["fee"] / 1e9,
                sol_chg=sol_chg, pre_bal=pre_bal, post_bal=post_bal, tok=tok, nonce=nonce, cul=cul, cup=cup, cu=meta.get("computeUnitsConsumed"), tips=tips,
                xfers=xfers, router=router, pump_ix=pump_ix, ev=ev, names=names[:8], progs=progs, nclose=nclose, signer=keys[0], nsig=sum(1 for k in m["accountKeys"] if k.get("signer")))
if __name__ == "__main__":
    sigs = json.load(open(os.path.join(HERE, "sigs_CWiNFA.json")))
    rows = []; miss = 0
    for s in sigs:
        if not os.path.exists(os.path.join(HERE, "txc", s["signature"] + ".json")): miss += 1; rows.append(dict(sig=s["signature"], slot=s["slot"], bt=s.get("blockTime"), missing=True)); continue
        rows.append(one(s["signature"]))
    rows.sort(key=lambda r: (r["slot"], r["sig"]))
    json.dump(dict(wallet=W, txs=rows), open(os.path.join(HERE, "ledger_CWiNFA.json"), "w"))
    print(f"{len(rows)} txs, missing {miss}")

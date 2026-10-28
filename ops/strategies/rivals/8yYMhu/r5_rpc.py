#!/usr/bin/env python3
"""8yYMhu step 5 (read-only): parse DATA/gettx.jsonl (public RPC) into
 (1) r3-shaped rows for txs the recorder missed (rpc_tx.pkl, same fields as tx.pkl) and
 (2) an instruction-level decode of every fetched tx (ixs.pkl): durable nonce account, CU limit/price, Lighthouse asserts
     (SysvarClock slot <= deadline; bonding-curve account data u64 at offset 16 = virtual SOL reserves, lo/hi band), pump
     BuyV3/Buy/Sell args (u64, u64), tip transfer (account, lamports, relay), token-account seed, recent blockhash (= nonce value),
     pre/post wallet balance.
Lighthouse wire format seen (MEASURED on samples): ix data 0x0f|log|0x00 (Slot)|u64 value|op ; 0x03|log|n|{off u8? ,type 0x07=u64, u64, op}...
 op codes: 4 = >=, 5 = <= (Lighthouse IntegerOperator)."""
import json, pickle, struct, collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r3_decomp import parse as parse_ev, b58, DISC, CPI, RENTS, kind_of
W = "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3"
D = "/home/moiz/sniper-data/rivals/8yYMhu"
TIP = json.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/tipmap.json"))
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; CB = "ComputeBudget111111111111111111111111111111"; LH = "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + A58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def keys_of(res):
    msg = res["transaction"]["message"]; la = res["meta"].get("loadedAddresses") or {}
    return [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]] + (la.get("writable") or []) + (la.get("readonly") or [])
def lh_decode(d):
    """returns dict for the two Lighthouse shapes seen; raw hex otherwise"""
    try:
        if d[0] == 0x0f and len(d) >= 12:
            return dict(t="clock", field=d[2], value=struct.unpack_from("<Q", d, 3)[0], op=d[11])
        if d[0] == 0x03:
            n = d[2]; o = 3; out = []
            for _ in range(n):
                off = d[o]; typ = d[o + 1]; o += 2
                if typ == 0x07:
                    v = struct.unpack_from("<Q", d, o)[0]; o += 8; op = d[o]; o += 1
                    out.append((off, v, op))
                else:
                    return dict(t="data?", hex=d.hex())
            return dict(t="data", asserts=out)
    except Exception:
        pass
    return dict(t="?", hex=d.hex())
def decode(res):
    msg = res["transaction"]["message"]; meta = res["meta"]; keys = keys_of(res)
    signers = [k["pubkey"] for k in msg["accountKeys"] if isinstance(k, dict) and k.get("signer")]
    out = dict(sig=res["transaction"]["signatures"][0], slot=res["slot"], idx=res.get("transactionIndex"), bt=res["blockTime"], err=meta["err"],
               fee=meta["fee"], cu=meta.get("computeUnitsConsumed"), signer=signers[0] if signers else None, blockhash=msg.get("recentBlockhash"),
               nonce=None, cul=None, cup=None, ldl=None, lh=[], pump=[], tips=[], seed=None, newacc=None, transfers=[], ixorder=[])
    hi = keys.index(W) if W in keys else None
    out["pre"] = meta["preBalances"][hi] if hi is not None else None; out["post"] = meta["postBalances"][hi] if hi is not None else None
    for k, x in enumerate(msg["instructions"]):
        pid = x.get("programId"); p = x.get("parsed") if isinstance(x.get("parsed"), dict) else None
        if p and x.get("program") == "system":
            t = p.get("type"); info = p.get("info", {})
            out["ixorder"].append("sys:" + t)
            if t == "advanceNonce": out["nonce"] = info.get("nonceAccount")
            elif t == "createAccountWithSeed": out["seed"] = info.get("seed"); out["newacc"] = info.get("newAccount"); out["newacc_lamports"] = info.get("lamports")
            elif t == "transfer":
                dst = info.get("destination"); lam = int(info.get("lamports", 0))
                if dst in TIP: out["tips"].append((dst, lam, TIP[dst]))
                else: out["transfers"].append((info.get("source"), dst, lam))
            continue
        if p:
            out["ixorder"].append(f"{x.get('program')}:{p.get('type')}"); continue
        d = b58d(x.get("data", ""))
        if pid == CB:
            out["ixorder"].append(f"cb{d[0] if d else '?'}")
            if d and d[0] == 2: out["cul"] = struct.unpack_from("<I", d, 1)[0]
            elif d and d[0] == 3: out["cup"] = struct.unpack_from("<Q", d, 1)[0]
            elif d and d[0] == 4: out["ldl"] = struct.unpack_from("<I", d, 1)[0]
        elif pid == LH:
            out["ixorder"].append("lh"); dd = lh_decode(d); dd["accounts"] = x.get("accounts"); out["lh"].append(dd)
        elif pid == PUMP:
            out["ixorder"].append("pump")
            args = [struct.unpack_from("<Q", d, 8 + 8 * j)[0] for j in range((len(d) - 8) // 8)][:3]
            out["pump"].append(dict(disc=d[:8].hex(), args=args, accounts=x.get("accounts")))
        else:
            out["ixorder"].append(pid[:8])
    logs = meta.get("logMessages") or []
    out["ixn"] = [lg.split(": ", 2)[2] for lg in logs if lg.startswith("Program log: Instruction: ")]
    evs = []
    for g in meta.get("innerInstructions") or []:
        for x in g["instructions"]:
            if x.get("programId") == PUMP and "data" in x:
                d = b58d(x["data"])
                if d[:8] == CPI and d[8:16] == DISC and len(d) >= 8 + 225: evs.append(parse_ev(d[8:]))
    out["events"] = evs
    return out
def to_row(res, ins):
    """r3-shaped row for a tx (used for recorder-missed txs)"""
    meta = res["meta"]; keys = keys_of(res)
    sd_all = {k: meta["postBalances"][j] - meta["preBalances"][j] for j, k in enumerate(keys[:len(meta["preBalances"])])}
    own = ins["signer"] == W; ok = meta["err"] is None
    mine = [e for e in ins["events"] if e["user"] == W]
    tips = [(a, v) for a, v, r in ins["tips"]]
    tipsum = sum(v for a, v in tips) if ok else 0
    k = kind_of(own, ok, ins["ixn"])
    tb = []
    pre = {(b["mint"], b.get("owner")): int(b["uiTokenAmount"]["amount"]) for b in meta.get("preTokenBalances") or []}
    post = {(b["mint"], b.get("owner")): int(b["uiTokenAmount"]["amount"]) for b in meta.get("postTokenBalances") or []}
    for kk in set(pre) | set(post):
        if pre.get(kk, 0) != post.get(kk, 0): tb.append([kk[0], kk[1], pre.get(kk, 0), post.get(kk, 0)])
    mint = mine[0]["mint"] if mine else next((m for m, o, a, b in tb if o == W), None)
    r = dict(sig=ins["sig"], s=ins["slot"], i=ins["idx"], bt=ins["bt"], ok=ok, err=meta["err"], kind=k, own=own, signers=[ins["signer"]],
             txfee=meta["fee"] if own else 0, cu=ins["cu"], cup=ins["cup"], cul=ins["cul"], tips=tipsum, tip_acc=[a for a, v in tips], tip_amt=[v for a, v in tips],
             relay="+".join(sorted(set(TIP.get(a, "?") for a, v in tips))) or "none", progs=None, ixn="|".join(ins["ixn"]), mints=None, sd=sd_all.get(W, 0),
             nev=len(mine), mint=mint, events=mine, allev=len(ins["events"]), trade=0, rent_c=0, rent_x=0, other=0, tb=tb, src="rpc")
    if mine: r["trade"] = sum((-(x["sol"] + x["fee"] + x["cfee"]) if x["buy"] else (x["sol"] - x["fee"] - x["cfee"])) for x in mine)
    if own and ok:
        rest = r["sd"] - (r["trade"] - r["txfee"] - tipsum)
        r["rent_c"] = sum(v for a, v in sd_all.items() if a != W and v in RENTS and a not in dict(tips))
        r["rent_x"] = sum(-v for a, v in sd_all.items() if a != W and -v in RENTS)
        r["other"] = rest + r["rent_c"] - r["rent_x"]
    elif own: r["other"] = r["sd"] + r["txfee"]
    else: r["other"] = r["sd"]
    return r
if __name__ == "__main__":
    G = {}
    for l in open(f"{D}/gettx.jsonl"):
        try: j = json.loads(l)
        except Exception: continue
        if j.get("res"): G[j["sig"]] = (j["why"], j["res"])
    I = {}; R = []
    for sig, (why, res) in G.items():
        ins = decode(res); ins["why"] = why; I[sig] = ins
        r = to_row(res, ins); r["why"] = why; R.append(r)
    pickle.dump(I, open(f"{D}/ixs.pkl", "wb")); pickle.dump(R, open(f"{D}/rpc_tx.pkl", "wb"))
    print("fetched", len(G), collections.Counter(w for w, _ in G.values()))
    print("ix order patterns:", collections.Counter(("ok" if v["err"] is None else json.dumps(v["err"])[:40], "|".join(v["ixorder"])) for v in I.values()).most_common(12))

#!/usr/bin/env python3
# READ-ONLY deep look at one sniper wallet (owner's RPC via RPC_URLS). Per transaction: pump.fun buys/sells by the wallet,
# programs used (router), compute budget (CU price / limit), priority fee, tips by landing service (labelled transfers),
# quote currency of the bought token (SOL vs other: which mints moved), slot delta to the token's create, MC proxy.
# usage: RPC_URLS=... TIPMAP_JSON=... python3 -I deep.py <wallet> <out.json> [max_txs=400]
import sys, os, json, base64, collections, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); R1 = os.path.join(HERE, "..", "..", "run1")
src = open(os.path.join(R1, "bundlestudy.py")).read()
ns = {"__file__": os.path.join(R1, "bundlestudy.py"), "__name__": "bs"}
exec(compile(src[:src.index("\ndef one(")], "bundlestudy.py", "exec"), ns)
rpc, b58enc, b58dec, txmeta, label = ns["rpc"], ns["b58enc"], ns["b58dec"], ns["txmeta"], ns["label"]
W, OUT = sys.argv[1], sys.argv[2]; MAXT = int(sys.argv[3]) if len(sys.argv) > 3 else 400
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CB = "ComputeBudget111111111111111111111111111111"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
def events(tx):
    out = []
    for l in (tx.get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != DISC or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58enc(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58enc(raw[57:89]), vsol=u(97), vtok=u(105), creator=b58enc(raw[177:209]), evlen=len(raw)))
    return out
def one(s):
    t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    msg = t["transaction"]["message"]; meta = t["meta"]; la = meta.get("loadedAddresses") or {}
    keys = list(msg["accountKeys"]) + la.get("writable", []) + la.get("readonly", [])
    progs = [keys[ix["programIdIndex"]] for ix in msg["instructions"]]
    cu_price = cu_limit = None
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != CB: continue
        d = b58dec(ix["data"])
        if d[:1] == b"\x03": cu_price = int.from_bytes(d[1:9], "little")
        if d[:1] == b"\x02": cu_limit = int.from_bytes(d[1:5], "little")
    tm = txmeta(t)
    ev = [e for e in events(t) if e["user"] == W]
    # token balance changes of accounts owned by the wallet (quote currency detection)
    pre = {(b["accountIndex"]): b for b in meta.get("preTokenBalances") or []}; post = {(b["accountIndex"]): b for b in meta.get("postTokenBalances") or []}
    moved = collections.Counter()
    for i in set(pre) | set(post):
        b = post.get(i) or pre.get(i)
        if b.get("owner") != W: continue
        a0 = float(((pre.get(i) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0); a1 = float(((post.get(i) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0)
        moved[b["mint"]] += a1 - a0
    i_w = keys.index(W) if W in keys else None
    return dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), err=meta.get("err") is not None, progs=progs, cu_price=cu_price, cu_limit=cu_limit,
                prio=tm["prio"], tips=tm["tips"], payer=tm["payer"], nsig=len(tm["signers"]), ev=ev, moved=dict(moved),
                sol_chg=((meta["postBalances"][i_w] - meta["preBalances"][i_w]) / 1e9) if i_w is not None else None, inner_progs=sorted({keys[ix["programIdIndex"]] for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]}))
sigs, before = [], None
while len(sigs) < MAXT:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p]) or []
    if not r: break
    sigs += r; before = r[-1]["signature"]
    if len(r) < 1000: break
sigs = [s for s in sigs if s.get("err") is None][:MAXT]
with cf.ThreadPoolExecutor(8) as ex: T = [t for t in ex.map(one, sigs) if t]
buys = [t for t in T if any(e["buy"] for e in t["ev"])]
def delta(t):
    e = next(e for e in t["ev"] if e["buy"])
    r = rpc("getSignaturesForAddress", [e["mint"], {"before": t["sig"], "limit": 40}]) or []
    if len(r) < 40:
        t["create_slot"] = r[-1]["slot"] if r else t["slot"]; t["create_sig"] = r[-1]["signature"] if r else None; t["delta"] = t["slot"] - t["create_slot"]
    else: t["delta"] = None
    return t
with cf.ThreadPoolExecutor(8) as ex: list(ex.map(delta, buys))
json.dump(dict(wallet=W, txs=T), open(OUT, "w"))
print(f"{W}: {len(T)} ok txs fetched, {len(buys)} with a pump.fun buy by the wallet, {sum(1 for t in T if any(not e['buy'] for e in t['ev']))} with a sell")

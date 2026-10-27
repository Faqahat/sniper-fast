#!/usr/bin/env python3
# How do the rivals that beat us in live runs send? Per rival wallet: sample of its recent successful pump/pumpswap BUYS (signer = wallet):
# durable nonce (first ix = System AdvanceNonceAccount), how many nonce accounts, tip services on landed txs (= the routes that delivered),
# share with no tip, CU price, and "double landings" (2+ landed buys of the same token within 2 slots = no dedupe). Read-only RPC.
import json, os, time, urllib.request, collections, statistics, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
PUMP = {"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p):
    for i in range(7):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.0 * (i + 1))
def one(w):
    sigs = rpc("getSignaturesForAddress", [w, {"limit": 400}]) or []
    sigs = [s for s in sigs if s.get("err") is None]
    rows = []
    for s in sigs:
        if len(rows) >= 40: break
        t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}]); time.sleep(0.15)
        if not t: continue
        m = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}; k = m["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        if k[0] != w: continue
        progs = {k[i["programIdIndex"]] for i in m["instructions"]} | {k[i["programIdIndex"]] for g in t["meta"].get("innerInstructions") or [] for i in g["instructions"]}
        if not (progs & PUMP): continue
        # buy? the wallet's token balance of some non-SOL mint went up
        pre = {(b["mint"]): int(b["uiTokenAmount"]["amount"]) for b in t["meta"].get("preTokenBalances") or [] if b.get("owner") == w}
        post = {(b["mint"]): int(b["uiTokenAmount"]["amount"]) for b in t["meta"].get("postTokenBalances") or [] if b.get("owner") == w}
        up = [mm for mm in post if post[mm] > pre.get(mm, 0) and not mm.startswith("So1111")]
        if not up: continue
        ix0 = m["instructions"][0]; d0 = dec(ix0["data"])
        nonce = k[ix0["programIdIndex"]] == SYS and len(d0) >= 4 and int.from_bytes(d0[:4], "little") == 4
        nacct = k[ix0["accounts"][0]] if nonce else None
        tips = sorted({TIP[k[i["accounts"][1]]] for i in m["instructions"] if k[i["programIdIndex"]] == SYS and len(i["accounts"]) > 1 and k[i["accounts"][1]] in TIP})
        cup = 0
        for i in m["instructions"]:
            if k[i["programIdIndex"]] == CB:
                d = dec(i["data"])
                if d and d[0] == 3: cup = int.from_bytes(d[1:9], "little")
        rows.append(dict(slot=t["slot"], mint=up[0], nonce=nonce, nacct=nacct, tips=tips, cup=cup, nsig=m["header"]["numRequiredSignatures"]))
    return w, rows
if __name__ == "__main__":
    W = json.load(open("rivals.json"))
    with cf.ThreadPoolExecutor(6) as ex: R = dict(ex.map(one, W))
    json.dump(R, open("rival_send.json", "w"))
    print("wallet (wins vs us)                          buys  nonce  nonce-accts  routes seen (landed tip services)                     no-tip  CU price med  double-landings")
    allsvc = collections.Counter(); tot = 0; nn = 0
    for w in W:
        v = R[w]
        if not v: print(f"  {w}  no buys sampled"); continue
        svc = collections.Counter(s for r in v for s in (r["tips"] or ["no tip"]))
        multi = sum(1 for r in v if len(r["tips"]) > 1)
        dbl = sum(1 for a in v for b in v if a is not b and a["mint"] == b["mint"] and abs(a["slot"] - b["slot"]) <= 2) // 2
        tot += len(v); nn += sum(r["nonce"] for r in v); allsvc.update(svc)
        print(f"  {w}  {len(v):3d}  {sum(r['nonce'] for r in v)/len(v):4.0%}  {len({r['nacct'] for r in v if r['nacct']}):3d}  {len([s for s in svc if s != 'no tip']):2d} relays: {dict(svc.most_common(6))}  "
              f"{svc.get('no tip', 0)/len(v):4.0%}  {statistics.median(r['cup'] for r in v):>10.0f}  {dbl}  (tx with 2+ tips: {multi})")
    print(f"\nALL: buys {tot} | durable nonce {nn/tot:.0%} | landed via: {dict(allsvc.most_common(12))}")

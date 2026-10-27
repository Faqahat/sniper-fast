#!/usr/bin/env python3
# haqq SEND PATHS, part 3 (READ-ONLY RPC, small): getTransaction on a stratified sample of haqq's txs from the recording
# (failed buys, landed buys, landed sells) to read what the recording cannot: the tip instruction of FAILED copies (the transfer
# is rolled back, so its balance change is gone but the instruction stays), the durable-nonce instruction, the compute-budget
# instructions and the router instruction shape. <= 5 requests/s. The RPC URL is read from the config file and never printed.
# usage: python3 -I p3_rpc_sample.py N_FAIL N_BUY N_SELL
import sys, os, json, time, random, urllib.request, collections
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p, tries=4):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
nf, nb, ns = (int(x) for x in sys.argv[1:4])
led = json.load(open(f"{H.OUT}/ledger.json"))
random.seed(7)
fails = [r for r in led if r["kind"] == "fail" and "Buy" in r["ixn"] and r["run"] in ("R3", "R4")]
buys = [r for r in led if r["kind"] == "buy" and r["run"] in ("R3", "R4")]
sells = [r for r in led if r["kind"] == "sell" and r["run"] in ("R3", "R4")]
sample = [("fail_buy", r) for r in random.sample(fails, min(nf, len(fails)))] + [("buy", r) for r in random.sample(buys, nb)] + [("sell", r) for r in random.sample(sells, ns)]
out = open(f"{H.OUT}/rpc_sample.jsonl", "w"); t_last = 0.0; n_ok = 0
for kind, r in sample:
    dt = time.time() - t_last
    if dt < 0.21: time.sleep(0.21 - dt)
    t_last = time.time()
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: continue
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    ixs = []; tips = []; nonce = None; cup = cul = None
    for n_, ix in enumerate(msg["instructions"]):
        pr = keys[ix["programIdIndex"]]; d = b58dec(ix["data"])
        name = pr[:8]
        if pr == SYS and len(d) >= 4:
            typ = int.from_bytes(d[:4], "little")
            if typ == 4: nonce = keys[ix["accounts"][0]]; name = "AdvanceNonce"
            elif typ == 2 and len(d) >= 12:
                to = keys[ix["accounts"][1]]; amt = int.from_bytes(d[4:12], "little"); name = "transfer"
                tips.append((H.svc_of(to), amt, to in H.TIP or to.startswith("noz")))
        elif pr == CB and d:
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little"); name = "CU price"
            elif d[0] == 2: cul = int.from_bytes(d[1:5], "little"); name = "CU limit"
        elif pr.startswith("haqqq"): name = f"router:{d[:1].hex()}:len{len(d)}:accs{len(ix['accounts'])}"
        ixs.append(name)
    rec = dict(kind=kind, sig=r["sig"], s=r["s"], i=r["i"], nsig=len(t["transaction"]["signatures"]), nkeys=len(keys), alt=bool(la.get("writable") or la.get("readonly")),
               ixs=ixs, tips=tips, nonce=nonce, cup=cup, cul=cul, err=t["meta"].get("err"), fee=t["meta"].get("fee"), ver=t.get("version"))
    out.write(json.dumps(rec) + "\n"); n_ok += 1
out.close()
print("fetched", n_ok, "of", len(sample))

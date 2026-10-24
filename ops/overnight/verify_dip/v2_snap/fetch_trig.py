#!/usr/bin/env python3
# READ-ONLY RPC: fetch the trigger (big sell) transaction of each dip event and classify how a shred-only engine would see it:
#   top   = the pump.fun sell is a TOP-LEVEL instruction (decodable straight from shreds: mint, user, token amount)
#   routed = the sell runs inside another program (CPI); records which outer program carries the mint (the "router")
# RPC = owner's endpoint (~/.config/sniper/ck_rpc_url, never printed). Resumable (skips sigs already in OUT).
# usage: python3 -I fetch_trig.py trig_sigs.jsonl trig_tx.jsonl
import sys, os, json, time, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=30))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
    return None
IN, OUT = sys.argv[1], sys.argv[2]
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["sig"])
        except Exception: pass
todo = {}
for l in open(IN):
    e = json.loads(l)
    if e.get("sig") and e["sig"] not in done: todo[e["sig"]] = e["m"]
print("to fetch", len(todo), "already", len(done), flush=True)
def one(item):
    sig, mint = item
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return dict(sig=sig, kind="nofetch")
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    outer = []; top = None; router = None
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]; accs = [keys[a] for a in ix["accounts"]]; d = b58dec(ix["data"])
        outer.append(p)
        if p == PUMP and mint in accs and top is None: top = dict(disc=d[:8].hex(), dlen=len(d), nacc=len(accs), mintpos=accs.index(mint))
        elif p != PUMP and mint in accs and router is None: router = dict(prog=p, dlen=len(d), nacc=len(accs), disc=d[:8].hex(), mintpos=accs.index(mint))
    return dict(sig=sig, kind="top" if top else ("routed" if router else "other"), top=top, router=router, outer=outer,
                nsig=len(t["transaction"]["signatures"]), signer=msg["accountKeys"][0], cu=t["meta"].get("computeUnitsConsumed"), fee=t["meta"].get("fee"))
n = 0
with open(OUT, "a") as f, cf.ThreadPoolExecutor(16) as ex:
    for r in ex.map(one, todo.items()):
        f.write(json.dumps(r) + "\n"); n += 1
        if n % 500 == 0: print("fetched", n, flush=True)
print("fetched", n)

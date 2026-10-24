#!/usr/bin/env python3
# READ-ONLY: fetch a random sample of pump.fun trade transactions on young launches (R2) with full instruction data + logs,
# to build and validate a decoder of every pump buy/sell instruction variant (for the dip shadow binary).
# RPC = owner's endpoint (~/.config/sniper/ck_rpc_url, never printed). -> dipshadow/sample_txs.jsonl
import sys, os, json, random, time, urllib.request, concurrent.futures as cf
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
OUT = "/home/moiz/sniper/ops/overnight/dipshadow/sample_txs2.jsonl"
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=30))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
    return None
L = rp.load_launches(); rnd = random.Random(11)
ms = [m for m, c in L.items() if c["run"] == "R2"]; rnd.shuffle(ms)
picked = []; seen = set()
for b in sorted({rp.bucket(m) for m in ms[:3000]})[:64]:
    bm = {m for m in ms[:3000] if rp.bucket(m) == b}
    for m, tr in rp.read_bucket("R2", b, bm).items():
        S = L[m]["slot"]
        for t in tr:
            if t["s"] - S > 600 or t["sig"] in seen: continue
            if rnd.random() < 0.05: picked.append((t["sig"], m, int(t["buy"]), t["sol"], t["tok"], t["user"])); seen.add(t["sig"])
picked = picked[:1500]
print("sample size", len(picked), flush=True)
def one(x):
    sig, m, buy, sol, tok, user = x
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    return dict(sig=sig, mint=m, ev_buy=buy, ev_sol=sol, ev_tok=tok, ev_user=user, tx=t)
with open(OUT, "w") as f, cf.ThreadPoolExecutor(16) as ex:
    n = 0
    for r in ex.map(one, picked):
        f.write(json.dumps(r) + "\n"); n += 1
print("fetched", n)

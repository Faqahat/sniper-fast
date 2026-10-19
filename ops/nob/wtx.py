#!/usr/bin/env python3
# READ-ONLY. getTransaction for every signature of the target wallet (ok and failed), keep a compact record:
# wallet SOL delta, fee, cu price, tips, pump TradeEvents (all mints in the tx), mints touched.
# usage: wtx.py <wsigs.jsonl> <out.jsonl> [workers]
import sys, json, os, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc, events, tx_summary, load_tipmap, PUMP

W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
INP, OUT = sys.argv[1], sys.argv[2]
NW = int(sys.argv[3]) if len(sys.argv) > 3 else 8
tipmap = load_tipmap()
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["sig"])
        except Exception:
            pass
sigs = []
seen = set()
for l in open(INP):
    x = json.loads(l)
    if x["signature"] in seen or x["signature"] in done:
        continue
    seen.add(x["signature"])
    sigs.append(x)
print("todo", len(sigs), "done", len(done), flush=True)
out = open(OUT, "a")
lk = threading.Lock()
cnt = [0]


def work(x):
    t = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    rec = {"sig": x["signature"], "slot": x["slot"], "err": x["err"], "bt": x.get("bt")}
    if not isinstance(t, dict) or "transaction" not in t:
        rec["fail"] = str(t)[:100]
    else:
        meta = t.get("meta") or {}
        s, keys = tx_summary(t, tipmap)
        try:
            i = keys.index(W)
            rec["dsol"] = meta["postBalances"][i] - meta["preBalances"][i]
            rec["pre"] = meta["preBalances"][i]
        except Exception:
            rec["dsol"] = None
        tr, cr = events(meta.get("logMessages"))
        rec.update(fee=s["fee"], cu_price=s["cu_price"], cu_limit=s["cu_limit"], tips=s["tips"], keytip=s["keytip"],
                   payer=s["payer"], signers=s["signers"], progs=s["progs"], cuu=s["cuu"])
        rec["ev"] = tr
        rec["cr"] = [c["mint"] for c in cr]
        # candidate mints touched (pump mints end with 'pump' usually; keep keys ending in pump)
        rec["mints"] = sorted({k for k in keys if k.endswith("pump") or k.endswith("bonk")})
        # token balance changes of the wallet
        tb = {}
        for b in meta.get("preTokenBalances") or []:
            if b.get("owner") == W:
                tb.setdefault(b["mint"], [0, 0])[0] = int(b["uiTokenAmount"]["amount"])
        for b in meta.get("postTokenBalances") or []:
            if b.get("owner") == W:
                tb.setdefault(b["mint"], [0, 0])[1] = int(b["uiTokenAmount"]["amount"])
        rec["tok"] = tb
    with lk:
        out.write(json.dumps(rec) + "\n")
        out.flush()
        cnt[0] += 1
        if cnt[0] % 500 == 0:
            print(time.strftime("%H:%M:%S"), cnt[0], "/", len(sigs), flush=True)


with ThreadPoolExecutor(max_workers=NW) as ex:
    list(ex.map(work, sigs))
print("FINISHED", cnt[0], flush=True)

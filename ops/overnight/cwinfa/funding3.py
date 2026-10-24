#!/usr/bin/env python3
# READ-ONLY (public RPC, ~1.6 req/s): CWiNFA's life before the owner's RPC horizon from a time-spread sample of its txs
# (balance trajectory, which programs it used when -> when the sniper started, router used), the first funder's activity
# level, and a time-spread sample of the router's upgrade key A5GQaNc3... (what it did between August and October).
import os, sys, json, collections, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rpcw
W = rpcw.W; DEV = "A5GQaNc37XMKPhn1hbzc12cvBaXj7Uk1qNmMeS9pRfAz"; FUNDER = "iGdFcQoyR2MwbXMHQskhmNsqddZ6rinsipHc4TNSdwu"
def tx(sig):
    try: return rpcw.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=rpcw.PUB)
    except Exception: return None
def summ(t, who):
    if not t: return None
    m = t["transaction"]["message"]; keys = [k["pubkey"] for k in m["accountKeys"]]; meta = t["meta"]; i = keys.index(who) if who in keys else None
    xf = []
    for ix in list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]:
        p = ix.get("parsed")
        if isinstance(p, dict) and isinstance(p.get("info"), dict) and "lamports" in p["info"] and (p["info"].get("source") == who or p["info"].get("destination") == who): xf.append([p["info"].get("source"), p["info"].get("destination"), p["info"]["lamports"] / 1e9])
    return dict(sig=t["transaction"]["signatures"][0], bt=t.get("blockTime"), slot=t["slot"], signer=keys[0], err=meta.get("err") is not None, v=t.get("version"),
                pre=meta["preBalances"][i] / 1e9 if i is not None else None, post=meta["postBalances"][i] / 1e9 if i is not None else None,
                progs=sorted({ix.get("programId") for ix in m["instructions"]}), names=[l.split("Instruction: ")[1] for l in (meta.get("logMessages") or []) if "Instruction: " in l][:5], xf=xf[:4])
OUT = {}
old = json.load(open(os.path.join(HERE, "sigs_CWiNFA_old.json")))
step = max(1, len(old) // 45)
OUT["cw_sample"] = [summ(tx(s["signature"]), W) for s in old[::step][:45]]
try:
    r = rpcw.rpc("getSignaturesForAddress", [FUNDER, {"limit": 1000}], ep=rpcw.PUB)
    OUT["funder"] = dict(n=len(r), newest=r[0].get("blockTime") if r else None, oldest=r[-1].get("blockTime") if r else None)
except Exception as e: OUT["funder"] = dict(error=str(e)[:100])
dev = []; before = None
for i in range(20):
    p = {"limit": 1000}
    if before: p["before"] = before
    try: r = rpcw.rpc("getSignaturesForAddress", [DEV, p], ep=rpcw.PUB)
    except Exception: break
    if not r: break
    dev += r; before = r[-1]["signature"]
    if len(r) < 1000: break
step = max(1, len(dev) // 25)
OUT["dev_sample"] = [summ(tx(s["signature"]), DEV) for s in dev[::step][:25]]
OUT["dev_n"] = len(dev); OUT["dev_failed"] = sum(1 for s in dev if s.get("err") is not None)
json.dump(OUT, open(os.path.join(HERE, "funding3.json"), "w"), indent=1)
f = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M") if t else "?"
for k in ("cw_sample", "dev_sample"):
    print("==", k)
    for s in OUT[k]:
        if s: print(f"  {f(s['bt'])} v{s['v']} err {s['err']} bal {s['pre']} -> {s['post']} signer {s['signer'][:6]} progs {[p[:6] for p in s['progs'] if not p.startswith('Compute')]} {s['names'][:3]} xf {[(a[:6], b[:6], round(l, 4)) for a, b, l in s['xf']][:2]}")
print("funder", OUT["funder"], "dev sigs", OUT["dev_n"], "failed", OUT["dev_failed"])

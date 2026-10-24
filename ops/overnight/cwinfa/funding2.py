#!/usr/bin/env python3
# READ-ONLY (public mainnet-beta RPC, ~1.6 req/s): CWiNFA's full history start (first transactions = funding) and the
# history of A5GQaNc3... (upgrade authority of CWiNFA's router program AND authority of its address lookup table).
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rpcw
W = rpcw.W; DEV = "A5GQaNc37XMKPhn1hbzc12cvBaXj7Uk1qNmMeS9pRfAz"
def page_all(addr, before=None, cap=150, tag=""):
    out = []
    for i in range(cap):
        p = {"limit": 1000}
        if before: p["before"] = before
        try: r = rpcw.rpc("getSignaturesForAddress", [addr, p], ep=rpcw.PUB)
        except Exception as e: print(tag, "page error", str(e)[:120], flush=True); break
        if not r: break
        out += r; before = r[-1]["signature"]
        if i % 10 == 0: print(f"  {tag} page {i}: slots {r[0]['slot']}..{r[-1]['slot']}", flush=True)
        if len(r) < 1000: break
    return out
def tx(sig):
    try: return rpcw.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=rpcw.PUB)
    except Exception: return None
def summarize(t, who):
    if not t: return None
    m = t["transaction"]["message"]; keys = [k["pubkey"] for k in m["accountKeys"]]; meta = t["meta"]
    i = keys.index(who) if who in keys else None
    xf = []
    for ix in list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]:
        p = ix.get("parsed")
        if isinstance(p, dict) and isinstance(p.get("info"), dict) and "lamports" in p["info"]: xf.append([p["info"].get("source"), p["info"].get("destination") or p["info"].get("newAccount"), p["info"]["lamports"] / 1e9, p.get("type")])
    return dict(sig=t["transaction"]["signatures"][0], slot=t["slot"], bt=t.get("blockTime"), signer=keys[0], err=meta.get("err") is not None,
                sol_chg=(meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else None, pre=meta["preBalances"][i] / 1e9 if i is not None else None,
                xfers=xf, progs=sorted({ix.get("programId") for ix in m["instructions"]}), names=[l.split("Instruction: ")[1] for l in (meta.get("logMessages") or []) if "Instruction: " in l][:6])
OUT = {}
old = json.load(open(os.path.join(HERE, "sigs_CWiNFA_old.json")))
more = page_all(W, before=old[-1]["signature"], cap=150, tag="CWiNFA")
allold = old + more
json.dump(allold, open(os.path.join(HERE, "sigs_CWiNFA_old.json"), "w"))
OUT["cw_total_sigs_before_horizon"] = len(allold); OUT["cw_first_slot"] = allold[-1]["slot"] if allold else None; OUT["cw_first_bt"] = allold[-1].get("blockTime") if allold else None
OUT["cw_first_txs"] = [summarize(tx(s["signature"]), W) for s in list(reversed(allold))[:10]]
dev = page_all(DEV, cap=20, tag="A5GQ")
OUT["dev_sigs"] = len(dev); OUT["dev_span"] = [dev[-1]["slot"], dev[0]["slot"], dev[-1].get("blockTime"), dev[0].get("blockTime")] if dev else None
sample = list(reversed(dev))[:15] + dev[:10]
OUT["dev_txs"] = [summarize(tx(s["signature"]), DEV) for s in sample]
json.dump(OUT, open(os.path.join(HERE, "funding2.json"), "w"), indent=1)
print(json.dumps(OUT)[:3000])

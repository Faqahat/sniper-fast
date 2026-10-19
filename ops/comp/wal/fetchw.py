# READ-ONLY. Pull every 4yFAz signature still in the RPC ledger, then every tx (ok + failed), compact.
import sys, json, os, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/nob"); sys.path.insert(0, "/root/indep")
from nrpc import rpc
from common import b58dec, events, tx_summary, load_tipmap
W = sys.argv[1]
D = "/root/comp/wal/" + sys.argv[1][:8] + "_"
minslot = rpc("minimumLedgerSlot", []); cut = max(minslot + 2000, rpc("getSlot", []) - int(sys.argv[2]) * 16600)
sigs = []
if os.path.exists(D + "sigs.jsonl"):
    sigs = [json.loads(l) for l in open(D + "sigs.jsonl")]
else:
    before = None
    while True:
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [W, p])
        if not isinstance(r, list) or not r: break
        sigs += [s for s in r if s["slot"] >= cut]
        before = r[-1]["signature"]
        print("sigs", len(sigs), r[-1]["slot"], flush=True)
        if r[-1]["slot"] < cut or len(sigs) > 20000: break
    with open(D + "sigs.jsonl", "w") as f:
        for s in sigs: f.write(json.dumps({"sig": s["signature"], "slot": s["slot"], "err": s["err"], "bt": s.get("blockTime")}) + "\n")
    sigs = [json.loads(l) for l in open(D + "sigs.jsonl")]
tipmap = load_tipmap()
done = set()
if os.path.exists(D + "tx.jsonl"):
    done = {json.loads(l)["sig"] for l in open(D + "tx.jsonl")}
todo = sorted([s for s in sigs if s["sig"] not in done and s["err"] != {"InstructionError": [3, {"Custom": 0}]}], key=lambda s: s["err"] is not None)
print("todo", len(todo), flush=True)
SKIP = re.compile(r"invoke \[|success$|consumed \d+ of")

def work(s):
    t = rpc("getTransaction", [s["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not isinstance(t, dict) or "transaction" not in t: return None
    meta = t["meta"]; msg = t["transaction"]["message"]
    summ, keys = tx_summary(t, tipmap)
    ixs = []
    for ix in msg["instructions"]:
        pid = keys[ix["programIdIndex"]]
        if pid.startswith("ComputeBudget"): continue
        raw = b58dec(ix["data"])
        acc = [keys[a] for a in ix["accounts"]]
        ixs.append({"p": pid, "d": raw.hex()[:240], "na": len(acc), "acc": acc if pid not in ("11111111111111111111111111111111",) else acc[:2]})
    tr, cr = events(meta.get("logMessages"))
    pre = meta["preBalances"][0]; post = meta["postBalances"][0]
    logs = [l[:220] for l in (meta.get("logMessages") or []) if not l.startswith("Program data") and not SKIP.search(l)]
    return {"sig": s["sig"], "slot": t["slot"], "bt": t.get("blockTime"), "err": meta.get("err"), "fee": meta["fee"], "dsol": post - pre,
            "pre": pre, "cu_price": summ["cu_price"], "cu_limit": summ["cu_limit"], "tips": summ["tips"], "cuu": summ["cuu"],
            "ixs": ixs, "ev": tr, "mints": sorted({k for k in keys if k.endswith("pump")}), "logs": logs[-12:]}

with ThreadPoolExecutor(3) as ex, open(D + "tx.jsonl", "a") as f:
    n = 0
    for r in ex.map(work, todo):
        n += 1
        if r: f.write(json.dumps(r) + "\n")
        if n % 500 == 0: print("tx", n, flush=True); f.flush()
print("DONE", flush=True)

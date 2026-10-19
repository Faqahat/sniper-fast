# READ-ONLY. Per mint 4yFAz bought: ordered "tape" of every tx touching the mint from the create through his last sell
# (blocks capped at buy_slot+CAP). Output tape.jsonl. usage: tape.py [limit_mints]
import sys, json, os, collections, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/nob"); sys.path.insert(0, "/root/indep")
import nrpc
if os.environ.get("RMR_RPC_URL"): nrpc.URL = os.environ["RMR_RPC_URL"]
from nrpc import rpc
from common import events, tx_summary, load_tipmap, is_vote
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
D = "/root/sizing/"; CAP = int(os.environ.get("CAP", "30"))
tipmap = load_tipmap()
nodes = {x["pubkey"]: x.get("clientId", "?") for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
txs = [json.loads(l) for l in open(D + "tx.jsonl")]
by = collections.defaultdict(lambda: {"buys": [], "sells": []})
for t in txs:
    if t["err"]: continue
    for e in t["ev"]:
        if e["user"] == W:
            by[e["mint"]]["buys" if e["buy"] else "sells"].append({"sig": t["sig"], "slot": t["slot"], "bt": t["bt"]})
mints = [(m, v) for m, v in by.items() if v["buys"]]
mints.sort(key=lambda x: -min(b["slot"] for b in x[1]["buys"]))
if len(sys.argv) > 1: mints = mints[:int(sys.argv[1])]
done = set()
import glob
for fn in glob.glob(D + "tape*.jsonl"):
    if "old" in fn: continue
    for l in open(fn):
        try: done.add(json.loads(l)["mint"])
        except Exception: pass
SH, NSH = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARD", "1"))
mints = [x for i, x in enumerate(mints) if x[0] not in done and i % NSH == SH]
print("mints", len(mints), flush=True)
_blk = {}
def blk(s):
    r = rpc("getBlock", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False, "commitment": "confirmed"}], timeout=120)
    return r if isinstance(r, dict) and "transactions" in r else None

def rows(b, slot, mint):
    out, nv = [], -1
    for t in b["transactions"]:
        if is_vote(t): continue
        nv += 1
        msg = t["transaction"]["message"]; meta = t.get("meta") or {}
        la = meta.get("loadedAddresses") or {}
        if mint not in msg["accountKeys"] and mint not in la.get("writable", []) and mint not in la.get("readonly", []): continue
        ok = meta.get("err") is None
        tr, cr = events(meta.get("logMessages")) if ok else ([], [])
        s, keys = tx_summary(t, tipmap)
        out.append({"slot": slot, "i": nv, "sig": s["sig"][:24], "payer": s["payer"], "his": W in s["signers"], "ok": ok,
                    "create": any(c["mint"] == mint for c in cr), "creator": next((c["creator"] for c in cr if c["mint"] == mint), None),
                    "ev": [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"], e["vtok"]] for e in tr if e["mint"] == mint],
                    "cu": s["cu_price"], "cul": s["cu_limit"], "fee": s["fee"], "tips": [[x[0], x[1]] for x in s["tips"]]})
    return out, nv + 1

def work(item):
    mint, v = item
    b0 = min(v["buys"], key=lambda b: b["slot"]); sb = b0["slot"]
    last = max([x["slot"] for x in v["sells"]] or [sb])
    tape, cslot, nnv = [], None, {}
    for s in (sb, sb - 1, sb - 2, sb - 3):
        b = blk(s)
        if not b: continue
        r, n = rows(b, s, mint); nnv[s] = n
        if any(x["create"] for x in r):
            cslot = s; tape = r; break
    if cslot is None:
        return {"mint": mint, "missing": "create"}
    act = set()
    r = rpc("getSignaturesForAddress", [mint, {"limit": 1000, "until": b0["sig"]}]) if CAP > 0 else []
    if isinstance(r, list):
        for x in r: act.add(x["slot"])
    hi = min(last, sb + CAP)
    if isinstance(r, list) and len(r) >= 1000 and act and min(act) > sb:
        act |= set(range(sb, hi + 1))
    want = sorted(s for s in act | {sb} if cslot < s <= hi)
    for s in want:
        b = blk(s)
        if not b: continue
        r2, n = rows(b, s, mint); nnv[s] = n; tape += r2
    lead = rpc("getSlotLeaders", [cslot, sb - cslot + 1])
    lead = lead if isinstance(lead, list) else []
    return {"mint": mint, "cslot": cslot, "bslot": sb, "last_sell_slot": last, "cap": hi, "nact": len(act), "nnv": nnv,
            "leaders": [[l, nodes.get(l, "?")] for l in lead], "tape": tape}

lk = threading.Lock(); n = [0]
with ThreadPoolExecutor(1) as ex, open(D + f"tape_{SH}.jsonl", "a") as f:
    for r in ex.map(work, mints):
        f.write(json.dumps(r) + "\n"); f.flush()
        n[0] += 1
        if n[0] % 20 == 0: print(time.strftime("%H:%M:%S"), n[0], flush=True)
print("DONE", flush=True)

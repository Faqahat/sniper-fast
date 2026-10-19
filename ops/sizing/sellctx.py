# READ-ONLY. For each of 4yFAz's sells: all mint sigs between his buy and that sell (activity), and the trade events
# of up to NTX txs in the 2 slots before the sell. out: sellctx.jsonl
import sys, json, os, collections, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/nob"); sys.path.insert(0, "/root/indep")
import nrpc
if os.environ.get("RMR_RPC_URL"): nrpc.URL = os.environ["RMR_RPC_URL"]
from nrpc import rpc
from common import events
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
D = "/root/sizing/"; NTX = int(os.environ.get("NTX", "6"))
TX = [json.loads(l) for l in open(D + "tx.jsonl")]
buy, sells = {}, collections.defaultdict(list)
for t in sorted(TX, key=lambda t: t["slot"]):
    if t["err"]: continue
    for e in t["ev"]:
        if e["user"] == W:
            if e["buy"]: buy.setdefault(e["mint"], t)
            else: sells[e["mint"]].append(t)
jobs = [(m, buy[m], s) for m in buy for s in sells[m]]
done = set()
if os.path.exists(D + "sellctx.jsonl"):
    done = {json.loads(l)["sig"] for l in open(D + "sellctx.jsonl")}
jobs = [j for j in jobs if j[2]["sig"] not in done]
print("jobs", len(jobs), flush=True)

def gt(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not isinstance(t, dict) or "meta" not in t: return None
    tr, _ = events(t["meta"].get("logMessages"))
    k = t["transaction"]["message"]["accountKeys"]
    return {"payer": k[0], "ev": [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"], e["vtok"]] for e in tr]}

def work(j):
    m, b, s = j
    r = rpc("getSignaturesForAddress", [m, {"limit": 1000, "before": s["sig"], "until": b["sig"]}])
    r = r if isinstance(r, list) else []
    act = collections.Counter(x["slot"] for x in r)
    nok = sum(1 for x in r if x["err"] is None)
    near = [x for x in r if x["slot"] >= s["slot"] - 2 and x["err"] is None][:NTX]
    det = []
    for x in near:
        g = gt(x["signature"])
        if g: det.append({"slot": x["slot"], "sig": x["signature"][:16], **g})
    return {"mint": m, "sig": s["sig"], "slot": s["slot"], "bslot": b["slot"], "nsig": len(r), "nok": nok, "full": len(r) >= 1000,
            "act": sorted(act.items()), "near": det, "n_near_total": sum(1 for x in r if x["slot"] >= s["slot"] - 2 and x["err"] is None)}

with ThreadPoolExecutor(4) as ex, open(D + "sellctx.jsonl", "a") as f:
    n = 0
    for r in ex.map(work, jobs):
        f.write(json.dumps(r) + "\n"); n += 1
        if n % 100 == 0: print(time.strftime("%H:%M:%S"), n, flush=True); f.flush()
print("DONE", flush=True)

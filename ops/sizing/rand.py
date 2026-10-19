# READ-ONLY. Random universe: sample slots in the window, every pump create in the block, with the rest of slot S
# and slot S+1 rows for that mint. out: rand.jsonl. usage: rand.py N
import sys, json, os, random, time, base64
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/nob"); sys.path.insert(0, "/root/indep"); sys.path.insert(0, "/root/sizing")
import nrpc
if os.environ.get("RMR_RPC_URL"): nrpc.URL = os.environ["RMR_RPC_URL"]
from nrpc import rpc
from common import events, tx_summary, load_tipmap, is_vote, CREATE_DISC, b58enc
D = "/root/sizing/"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
tipmap = load_tipmap()
TX = [json.loads(l) for l in open(D + "tx.jsonl")]
lo, hi = min(t["slot"] for t in TX), max(t["slot"] for t in TX)
random.seed(7)
N = int(sys.argv[1])
slots = sorted(random.sample(range(lo, hi), N))
done = set()
if os.path.exists(D + "rand.jsonl"):
    done = {json.loads(l)["S"] for l in open(D + "rand.jsonl")}
slots = [s for s in slots if s not in done]

def blk(s):
    r = rpc("getBlock", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False, "commitment": "confirmed"}], timeout=60)
    return r if isinstance(r, dict) and "transactions" in r else None

def cflag(logs):
    out = {}
    for l in logs or []:
        if l.startswith("Program data: "):
            raw = base64.b64decode(l[14:] + "===")
            if raw[:8] != CREATE_DISC: continue
            o = 8
            for _ in range(3):
                n = int.from_bytes(raw[o:o + 4], "little"); o += 4 + n
            mint = b58enc(raw[o:o + 32]); o += 32 + 32
            user = b58enc(raw[o:o + 32]); o += 32
            creator = b58enc(raw[o:o + 32]); o += 32
            o += 40
            tokprog = b58enc(raw[o:o + 32]) if len(raw) >= o + 32 else None; o += 32
            flag = raw[o] if len(raw) > o else None
            tail = raw[o + 1:]
            quote = b58enc(tail[1:33]) if len(tail) >= 33 and any(tail[1:33]) else None
            out[mint] = {"creator": creator, "mayhem": bool(flag), "t22": tokprog and tokprog.startswith("Tokenz"), "quote": quote}
    return out

def rows_for(b, slot, mints):
    res = {m: [] for m in mints}
    nv = -1
    for t in b["transactions"]:
        if is_vote(t): continue
        nv += 1
        msg = t["transaction"]["message"]; meta = t.get("meta") or {}
        la = meta.get("loadedAddresses") or {}
        ks = set(msg["accountKeys"]) | set(la.get("writable", [])) | set(la.get("readonly", []))
        hit = [m for m in mints if m in ks]
        if not hit: continue
        ok = meta.get("err") is None
        tr, _ = events(meta.get("logMessages")) if ok else ([], [])
        s, keys = tx_summary(t, tipmap)
        cf = cflag(meta.get("logMessages")) if ok else {}
        for m in hit:
            res[m].append({"slot": slot, "i": nv, "payer": s["payer"], "his": W in s["signers"], "ok": ok, "create": m in cf,
                           "cinfo": cf.get(m), "ev": [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"], e["vtok"]] for e in tr if e["mint"] == m],
                           "cu": s["cu_price"], "fee": s["fee"], "tips": [[x[0], x[1]] for x in s["tips"]]})
    return res, nv + 1

def work(S):
    b = blk(S)
    if not b: return {"S": S, "missing": 1}
    mints = []
    for t in b["transactions"]:
        meta = t.get("meta") or {}
        if meta.get("err") is not None: continue
        if not any("Instruction: Create" in l for l in meta.get("logMessages") or []): continue
        mints += list(cflag(meta.get("logMessages")).keys())
    if not mints: return {"S": S, "n": 0}
    r0, n0 = rows_for(b, S, mints)
    b1 = blk(S + 1)
    r1, n1 = rows_for(b1, S + 1, mints) if b1 else ({m: [] for m in mints}, 0)
    return {"S": S, "n": len(mints), "nnv": [n0, n1], "m": {m: r0[m] + r1[m] for m in mints}}

with ThreadPoolExecutor(2) as ex, open(D + "rand.jsonl", "a") as f:
    n = 0
    for r in ex.map(work, slots):
        f.write(json.dumps(r) + "\n"); n += 1
        if n % 100 == 0: print(time.strftime("%H:%M:%S"), n, flush=True); f.flush()
print("DONE", flush=True)

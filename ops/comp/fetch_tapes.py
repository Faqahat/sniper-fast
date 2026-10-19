# READ-ONLY. Per launch: every successful tx touching the mint from the create slot S to S+W (getSignaturesForAddress + getTransaction),
# full pump TradeEvent fields (incl. fee bps), fees/CU/tips/system transfers, slot leaders. Output /root/comp/tapes_<set>.jsonl
import sys, json, os, time, base64, random, threading
sys.path.insert(0, "/root/indep")
from common import tx_summary, load_tipmap, b58enc, b58dec, TRADE_DISC, CB, SYS, PUMP
sys.path.insert(0, "/root/comp")
from mrpc import rpc, stats
from concurrent.futures import ThreadPoolExecutor
W = int(os.environ.get("W", "300")); CAPTX = int(os.environ.get("CAPTX", "3000")); TH = int(os.environ.get("TH", "2"))
SET = sys.argv[1]  # r2 | c
TM = load_tipmap()
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
import glob
recs = {}
for fn in sorted(glob.glob("/root/race/*_onchain.jsonl")):
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        b = r.get("b") or {}
        if "dev" not in b or r["mint"] in recs: continue
        host = (b.get("uri") or "").split("://")[-1].split("/")[0]
        dev = b["dev"] / 1e9; gs = b.get("gsol", 0) / 1e9
        moon = any(str(x[2]).startswith("moon") for x in b.get("tips", []))
        base = 0.49 <= dev <= 8.1 and not (host in BOT or host.endswith(".trycloudflare.com")) and "CreateV2" in (b.get("ins") or [])
        r["isr2"] = base and 2.95 <= gs <= 5.05 and moon
        r["isc"] = base and gs >= 2
        r["src"] = fn.split("/")[-1]
        recs[r["mint"]] = r
if SET == "r2": L = [r for r in recs.values() if r["isr2"]]
else: L = [r for r in recs.values() if r["isc"] and not r["isr2"]]
random.Random(7).shuffle(L)
out = f"/root/comp/tapes_{SET}.jsonl"
done = set()
for fn in glob.glob(f"/root/comp/tapes_{SET}*.jsonl"):
    for l in open(fn):
        try: done.add(json.loads(l)["mint"])
        except Exception: pass
if os.environ.get("SHARD"): out = f"/root/comp/tapes_{SET}_{os.environ['SHARD']}.jsonl"
L = [r for r in L if r["mint"] not in done]
SH, NSH = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARD", "1"))
LIM = int(os.environ.get("LIM", "100000"))
L = [r for i, r in enumerate(L[:LIM]) if i % NSH == SH]
print(SET, "todo", len(L), "done", len(done), flush=True)

def ptrade(raw):
    g = lambda a, b: int.from_bytes(raw[a:b], "little")
    if len(raw) < 225: return None
    return dict(mint=b58enc(raw[8:40]), sol=g(40, 48), tok=g(48, 56), buy=raw[56], user=b58enc(raw[57:89]), ts=g(89, 97), vsol=g(97, 105),
                vtok=g(105, 113), rsol=g(113, 121), fbps=g(161, 169), fee=g(169, 177), cbps=g(209, 217), cfee=g(217, 225))

def tx_row(t, mint):
    meta = t.get("meta") or {}
    s, keys = tx_summary(t, TM)
    ev = []; nother = 0
    for l in meta.get("logMessages") or []:
        if l.startswith("Program data: "):
            try: raw = base64.b64decode(l[14:] + "===")
            except Exception: continue
            if raw[:8] == TRADE_DISC:
                e = ptrade(raw)
                if not e: continue
                if e["mint"] == mint:
                    ev.append([e["buy"], e["user"], e["sol"], e["tok"], e["vsol"], e["vtok"], e["rsol"], e["fbps"], e["fee"], e["cbps"], e["cfee"], e["ts"]])
                else: nother += 1
    msg = t["transaction"]["message"]; nsig = msg["header"]["numRequiredSignatures"]
    xfers = []  # system transfers from a signer: [dst, lamports, top]
    def scan(ix, top):
        try: pid = keys[ix["programIdIndex"]]
        except Exception: return
        if pid != SYS: return
        try: raw = b58dec(ix["data"])
        except Exception: return
        acc = ix.get("accounts") or []
        if len(raw) >= 12 and int.from_bytes(raw[:4], "little") == 2 and len(acc) >= 2 and acc[0] < nsig:
            xfers.append([keys[acc[1]], int.from_bytes(raw[4:12], "little"), top])
    for ix in msg["instructions"]: scan(ix, 1)
    for inn in meta.get("innerInstructions") or []:
        for ix in inn.get("instructions") or []: scan(ix, 0)
    pre, post = meta.get("preBalances") or [0], meta.get("postBalances") or [0]
    return {"slot": t["slot"], "bt": t.get("blockTime"), "sig": s["sig"], "signers": s["signers"], "fee": s["fee"], "cup": s["cu_price"],
            "cul": s["cu_limit"], "cuu": s["cuu"], "tips": s["tips"], "xf": xfers, "ev": ev, "nother": nother, "dpay": post[0] - pre[0],
            "progs": s["progs"][:6], "ver": t.get("version")}

def anchor(mint, s0):
    for s in range(s0, s0 + 40):
        b = rpc("getBlock", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "accounts", "rewards": False, "commitment": "confirmed"}], timeout=60)
        if not isinstance(b, dict) or "transactions" not in b: continue
        for t in b["transactions"]:
            ks = [a["pubkey"] if isinstance(a, dict) else a for a in t["transaction"]["accountKeys"]]
            if mint in ks: return t["transaction"]["signatures"][0]
    return None

def get_sigs(mint, csig, S):
    out, before, jumped = [], None, False
    for page in range(60):
        p = {"limit": 1000, "until": csig}
        if before: p["before"] = before
        x = rpc("getSignaturesForAddress", [mint, p])
        if not isinstance(x, list): return None, "sigerr"
        if not x: break
        out += [s for s in x if s["slot"] <= S + W]
        before = x[-1]["signature"]
        if len(x) < 1000: break
        if not jumped and x[-1]["slot"] > S + W + 50:
            a = anchor(mint, S + W + 1); jumped = True
            if a: before = a
    return out, "ok"

def gtx(sig):
    for i in range(2):
        t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if isinstance(t, dict) and "transaction" in t: return t
    return None

lk = threading.Lock()
f = open(out, "a"); cnt = [0, 0]; t0 = time.time()

def work(r):
    b = r["b"]; S = b["slot"]; mint = r["mint"]
    sigs, st = get_sigs(mint, b["csig"], S)
    rec = {k: b.get(k) for k in ("slot", "bt", "csig", "cidx", "cnv", "nnv", "ntx", "name", "symbol", "uri", "creator", "user", "payer", "signers",
                                 "cu_price", "cu_limit", "fee", "tips", "dev", "base", "glued", "gsol", "gv", "later", "nlater", "ins")}
    rec.update(mint=mint, isr2=r["isr2"], isc=r["isc"], src=r["src"], srows=(r.get("s") or {}).get("rows"), st=st)
    n = 0
    if sigs is not None:
        ok = sorted([s for s in sigs if s["err"] is None], key=lambda s: s["slot"])
        rec["nsig_all"] = len(sigs); rec["nsig_ok"] = len(ok); rec["capped"] = len(ok) > CAPTX
        ok = ok[:CAPTX]
        res = [gtx(s["signature"]) for s in ok]
        rec["nmiss"] = sum(1 for x in res if x is None)
        rec["txs"] = [tx_row(t, mint) for t in res if t]
        n = len(ok)
        ld = rpc("getSlotLeaders", [S, W + 1])
        rec["leaders"] = ld if isinstance(ld, list) else None
    line = json.dumps(rec, separators=(",", ":")) + "\n"
    with lk:
        f.write(line); f.flush()
        cnt[0] += 1; cnt[1] += n
        if cnt[0] % 5 == 0:
            print(time.strftime("%H:%M:%S"), cnt[0], "tx", cnt[1], "%.1f tx/s" % (cnt[1] / (time.time() - t0)), stats(), flush=True)

def _stat():
    while True:
        time.sleep(30)
        print(time.strftime("%H:%M:%S"), "STAT done", cnt[0], "tx", cnt[1], stats(), flush=True)
threading.Thread(target=_stat, daemon=True).start()
with ThreadPoolExecutor(TH) as ex:
    list(ex.map(work, L))
print("DONE", flush=True)

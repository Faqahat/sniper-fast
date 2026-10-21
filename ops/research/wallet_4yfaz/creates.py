# READ-ONLY (host; public RPC): for every mint in <mints.json> ([{mint, first_sig, slot}]) find its pump.fun create tx
# (oldest signature of the mint before the given buy) and decode it: create slot, creator, name/symbol/uri, dev buy,
# top-level SOL transfers (tip / platform fee), cu limit/price, signers, programs. Output jsonl.
# usage: python3 creates.py <mints.json> <out.jsonl>   env THREADS=3
import sys, os, json, time, base64, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txs import rpc, b58dec, b58enc, trades, compact  # noqa: E402  (txs.py guards its main part)
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
MJ, OUT = sys.argv[1], sys.argv[2]


def bstr(d, o):
    n = int.from_bytes(d[o:o + 4], "little")
    if n > 400 or o + 4 + n > len(d): raise ValueError
    return d[o + 4:o + 4 + n].decode("utf8", "replace"), o + 4 + n


def parse_create(t):
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    ixs = list(msg["instructions"]) + [ix for g in meta.get("innerInstructions") or [] for ix in g["instructions"]]
    for ix in ixs:
        if keys[ix["programIdIndex"]] != PUMP: continue
        d = b58dec(ix["data"])
        try:
            name, o = bstr(d, 8); sym, o = bstr(d, o); uri, o = bstr(d, o)
            if not uri.startswith(("http", "ipfs")) and "/" not in uri: continue
            creator = b58enc(d[o:o + 32]) if len(d) >= o + 32 else None
            return dict(disc=d[:8].hex(), name=name, sym=sym, uri=uri, creator=creator, top=ix in msg["instructions"],
                        accts=[keys[a] for a in ix["accounts"][:3]], tail=d[o + 32:].hex())
        except Exception:
            continue
    return None


def job(m):
    sigs = []; before = m["first_sig"]
    for _ in range(5):
        res = rpc("getSignaturesForAddress", [m["mint"], {"limit": 1000, "before": before}])
        if res in (None, "ERR") or not res: break
        sigs += res; before = res[-1]["signature"]
        if len(res) < 1000: break
    if not sigs: return dict(mint=m["mint"], err="no older sigs (he was first?)")
    c = sigs[-1]
    t = rpc("getTransaction", [c["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if t in (None, "ERR"): return dict(mint=m["mint"], err="create tx fetch failed", csig=c["signature"])
    row = compact(c["signature"], t); row["create"] = parse_create(t)
    row.update(mint=m["mint"], n_before=len(sigs), n_before_ok=sum(1 for s in sigs if s.get("err") is None),
               sigs_before=[[s["signature"], s["slot"], s.get("err") is not None, s.get("transactionIndex")] for s in sigs[-60:]])
    return row


if __name__ == "__main__":
    M = json.load(open(MJ)); done = set()
    if os.path.exists(OUT):
        for l in open(OUT): done.add(json.loads(l)["mint"])
    todo = [m for m in M if m["mint"] not in done]; print("todo", len(todo), flush=True)
    fo = open(OUT, "a"); n = 0
    from concurrent.futures import as_completed
    with ThreadPoolExecutor(int(os.environ.get("THREADS", "3"))) as ex:
        for f in as_completed([ex.submit(job, m) for m in todo]):
            r = f.result()
            fo.write(json.dumps(r) + "\n"); fo.flush(); n += 1
            if n % 25 == 0: print(n, time.strftime("%H:%M:%S"), flush=True)
    print("DONE", n, flush=True)

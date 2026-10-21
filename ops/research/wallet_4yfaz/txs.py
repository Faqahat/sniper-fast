# READ-ONLY (host; public RPC): getTransaction for every successful signature in sigs.json -> compact rows
# (pump TradeEvents, wallet SOL delta, fee, CU, compute-budget limit/price, top-level SOL transfers = tips, programs).
# usage: python3 txs.py <sigs.json> <out.jsonl> [--failed N]   env THREADS=3
import sys, os, json, time, base64, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
EPS = ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"]
cool = {e: 0.0 for e in EPS}; lock = threading.Lock()
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}


def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n: n, r = divmod(n, 58); out.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + "".join(reversed(out))


def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + full


def rpc(meth, params):
    """publicnode first; a null result there (older than its ~23 h) or an error falls through to mainnet-beta."""
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    nulls = set()
    for i in range(16):
        with lock:
            cand = [e for e in EPS if e not in nulls] or EPS
            ep = min(cand, key=lambda e: cool[e]); wait = cool[ep] - time.time()
        if wait > 0: time.sleep(min(wait, 5))
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=data, headers={"content-type": "application/json", "user-agent": "curl/8.5.0"}), timeout=60))
            if "error" in r:
                with lock: cool[ep] = time.time() + 2 + i
                continue
            if r.get("result") is None:
                nulls.add(ep)
                if len(nulls) == len(EPS): return None
                continue
            return r["result"]
        except Exception as e:
            with lock: cool[ep] = time.time() + (6 if "429" in str(e) else 2) + min(i, 6)
    return "ERR"


def trades(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try: raw = base64.b64decode(l[14:] + "===")
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 129: continue
        g = lambda a, b: int.from_bytes(raw[a:b], "little")
        out.append(dict(mint=b58enc(raw[8:40]), sol=g(40, 48), tok=g(48, 56), buy=raw[56], user=b58enc(raw[57:89]), ts=g(89, 97),
                        vsol=g(97, 105), vtok=g(105, 113), rsol=g(113, 121), rtok=g(121, 129),
                        fee=g(161, 169) if len(raw) >= 169 else None, cfee=g(209, 217) if len(raw) >= 217 else None))
    return out


def compact(sig, t):
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    cul = cup = None; transfers = []; progs = []
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]; progs.append(p)
        d = b58dec(ix["data"])
        if p == CB and d:
            if d[0] == 2: cul = int.from_bytes(d[1:5], "little")
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
        if p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
            transfers.append([keys[ix["accounts"][0]], keys[ix["accounts"][1]], int.from_bytes(d[4:12], "little")])
    pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
    wi = keys.index(W) if W in keys else None
    wd = (post[wi] - pre[wi]) if wi is not None and wi < len(post) else None
    inner_tr = []
    for g in meta.get("innerInstructions") or []:
        for ix in g["instructions"]:
            if keys[ix["programIdIndex"]] == SYS:
                d = b58dec(ix["data"])
                if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
                    inner_tr.append([keys[ix["accounts"][0]], keys[ix["accounts"][1]], int.from_bytes(d[4:12], "little")])
    return dict(sig=sig, slot=t["slot"], bt=t.get("blockTime"), err=meta.get("err") is not None, fee=meta.get("fee"), cu=meta.get("computeUnitsConsumed"),
                cul=cul, cup=cup, payer=keys[0], signers=keys[:nsig], nkeys=len(msg["accountKeys"]), luts=len(msg.get("addressTableLookups") or []),
                nix=len(msg["instructions"]), progs=progs, transfers=transfers, inner_tr=inner_tr, wd=wd, trades=trades(meta.get("logMessages")),
                ver=t.get("version"), tidx=t.get("transactionIndex"))


if __name__ == "__main__":
    SIGS, OUT = sys.argv[1], sys.argv[2]
    S = json.load(open(SIGS))
    todo = [r for r in S if not r["err"]]
    if "--failed" in sys.argv:
        import random; random.seed(1); f = [r for r in S if r["err"]]; todo = random.sample(f, min(int(sys.argv[sys.argv.index("--failed") + 1]), len(f)))
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            try: done.add(json.loads(l)["sig"])
            except Exception: pass
    todo = [r for r in todo if r["sig"] not in done]
    print("to fetch", len(todo), flush=True)
    fo = open(OUT, "a"); wl = threading.Lock(); n = [0]


    def job(r):
        t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
        if t in (None, "ERR"): return r["sig"], t
        row = compact(r["sig"], t)
        with wl:
            fo.write(json.dumps(row) + "\n"); fo.flush(); n[0] += 1
            if n[0] % 100 == 0: print(n[0], time.strftime("%H:%M:%S"), flush=True)
        return r["sig"], "ok"


    with ThreadPoolExecutor(int(os.environ.get("THREADS", "3"))) as ex:
        bad = [s for s, res in ex.map(job, todo) if res != "ok"]
    print("DONE fetched", n[0], "missing", len(bad), flush=True)

# READ-ONLY (host; public RPC): getTransaction for each wallet's successful signatures (newest first, last HOURS h, at most
# MAXTX) plus a random sample of NFAIL failed ones -> <out_dir>/<wallet>.txs.jsonl (compact rows: pump TradeEvents, wallet
# SOL delta, fee, priority fee, CU, CU limit, top-level + inner SOL transfers, programs, signers, nonce use, tx version).
# Handles v1 transactions (transactionConfig instead of ComputeBudget instructions). Resumable. <= THREADS requests in flight.
# usage: python3 -I txs_multi.py <wallets.txt> <sigs_dir> <out_dir>    env HOURS=24 MAXTX=4000 NFAIL=40 THREADS=3
import sys, os, json, time, random, base64, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor

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


RATE = {EPS[0]: float(os.environ.get("RATE_PN", "12")), EPS[1]: float(os.environ.get("RATE_MB", "3.5"))}   # requests/s per endpoint
nxt = {e: 0.0 for e in EPS}


def slot_for(cand):
    """token-bucket pacing: take the endpoint whose next free send time is earliest (cool-downs push it back)."""
    with lock:
        now = time.time()
        ep = min(cand, key=lambda e: max(nxt[e], cool[e]))
        t = max(now, nxt[ep], cool[ep]); nxt[ep] = t + 1.0 / RATE[ep]
    if t > now: time.sleep(min(t - now, 5))
    return ep


def rpc(meth, params):
    """publicnode first; a null result there (older than its ~23 h) falls through to mainnet-beta; errors back off."""
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    nulls = set()
    for i in range(14):
        cand = [e for e in EPS if e not in nulls] or EPS
        ep = slot_for(cand)
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=data, headers={"content-type": "application/json", "user-agent": "curl/8.5.0"}), timeout=60))
            if "error" in r:
                if r["error"].get("code") == -32015: return "ERR"          # unsupported version: retrying cannot help
                with lock: cool[ep] = time.time() + 1 + i
                continue
            if r.get("result") is None:
                nulls.add(ep)
                if len(nulls) == len(EPS): return None
                continue
            return r["result"]
        except Exception as e:
            with lock: cool[ep] = time.time() + (1.0 if "429" in str(e) else 2) + min(i, 4) * 0.5
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


def compact(W, sig, t):
    msg = t["transaction"]["message"]; meta = t.get("meta") or {}
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    cul = cup = prio = None; transfers = []; progs = []; nonce = False
    cfg = msg.get("transactionConfig")
    if cfg:
        cul = cfg.get("computeUnitLimit"); prio = cfg.get("priorityFee")
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]; progs.append(p)
        d = b58dec(ix["data"])
        if p == CB and d:
            if d[0] == 2: cul = int.from_bytes(d[1:5], "little")
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
        if p == SYS and len(d) >= 4 and int.from_bytes(d[:4], "little") == 4: nonce = True       # AdvanceNonceAccount
        if p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
            transfers.append([keys[ix["accounts"][0]], keys[ix["accounts"][1]], int.from_bytes(d[4:12], "little")])
    if prio is None and cup is not None: prio = cup * (cul or 200000) // 1_000_000
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
                cul=cul, cup=cup, prio=prio, payer=keys[0], signers=keys[:nsig], nkeys=len(msg["accountKeys"]), luts=len(msg.get("addressTableLookups") or []),
                nix=len(msg["instructions"]), progs=progs, transfers=transfers, inner_tr=inner_tr, wd=wd, trades=trades(meta.get("logMessages")),
                ver=t.get("version"), nonce=nonce, tidx=t.get("transactionIndex"),
                errs=str(meta.get("err"))[:120] if meta.get("err") is not None else None)


if __name__ == "__main__":
    WF, SD, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
    HOURS = float(os.environ.get("HOURS", "24")); MAXTX = int(os.environ.get("MAXTX", "4000")); NFAIL = int(os.environ.get("NFAIL", "40"))
    TH = int(os.environ.get("THREADS", "3"))
    for W in [l.split()[0] for l in open(WF) if l.strip() and not l.startswith("#")]:
        sf = os.path.join(SD, W + ".sigs.json")
        if not os.path.exists(sf): print(W[:12], "no sigs yet", flush=True); continue
        S = json.load(open(sf)); t1 = max(r["bt"] for r in S if r["bt"]); t0 = t1 - HOURS * 3600
        ok = [r for r in S if not r["err"] and r["bt"] and r["bt"] >= t0][:MAXTX]
        fl = [r for r in S if r["err"] and r["bt"] and r["bt"] >= t0]
        random.seed(1); fs = random.sample(fl, min(NFAIL, len(fl)))
        fn = os.path.join(OUT, W + ".txs.jsonl")
        done = set()
        if os.path.exists(fn):
            for l in open(fn):
                try: done.add(json.loads(l)["sig"])
                except Exception: pass
        todo = [r for r in ok + fs if r["sig"] not in done]
        print(f"{W[:12]} ok {len(ok)} (of {sum(not r['err'] for r in S)}), failed sample {len(fs)} (of {len(fl)}); to fetch {len(todo)}", flush=True)
        if not todo: continue
        fo = open(fn, "a"); wl = threading.Lock(); n = [0]

        def job(r, W=W, fo=fo, wl=wl, n=n):
            t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            if t in (None, "ERR"): return "miss"
            row = compact(W, r["sig"], t)
            with wl:
                fo.write(json.dumps(row) + "\n"); fo.flush(); n[0] += 1
                if n[0] % 500 == 0: print(f"  {W[:8]} {n[0]} {time.strftime('%H:%M:%S')}", flush=True)
            return "ok"

        with ThreadPoolExecutor(TH) as ex:
            res = list(ex.map(job, todo))
        fo.close()
        print(f"{W[:12]} DONE fetched {n[0]} missing {res.count('miss')} {time.strftime('%H:%M:%S')}", flush=True)

# READ-ONLY (host, public RPC): the creator's PRIOR pump.fun launches, from the creator wallet's own transactions.
# For FILTERS3.md (number of prior creates, creator SOL at create, how fast the creator sold its earlier coins).
# For each creator wallet:
#   1. signatures (publicnode, up to 4 pages; its address index keeps only ~23 h -> one api.mainnet-beta page further back
#      when publicnode's list does not reach the creator's first watched launch)
#   2. every successful signature with slot <= the creator's last watched launch, NEWEST first -> getTransaction
#      (publicnode only; it keeps ~40 h of transactions -- the walk stops at the first one it no longer has) -> classify: pump create / pump buy / pump sell / other,
#      the mints, the creator's SOL pre/post and token deltas per mint.
#      Stop when 11 creates older than the creator's FIRST watched launch are found (bucket "10+" is then certain), or after
#      MAXTX transactions / MAXMB mainnet-beta calls (count is then a LOWER bound; flagged "trunc").
# Nothing is sent. <= 3 threads. Output is resumable.
# usage: python3 creator_creates.py <out.json> <creators_launches.json: {creator: [S, ...]}> [deadline_min] [priority.json]
import sys, json, time, threading, urllib.request, concurrent.futures as cf

OUT, INP = sys.argv[1], sys.argv[2]
DEADLINE = time.time() + 60 * float(sys.argv[3] if len(sys.argv) > 3 else 40)
PN, MB = "https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
MAXTX, MAXMB = 60, 25
lock = threading.Lock(); st = dict(calls=0, mb=0, err=0)
mb_lock = threading.Lock(); mb_last = [0.0]


def rpc(ep, method, params, tries=5):
    for a in range(tries):
        if ep == MB:                                            # be gentle with mainnet-beta: <= ~2 calls/s overall (it rate-limits hard)
            with mb_lock:
                w = mb_last[0] + 0.45 - time.time()
                if w > 0: time.sleep(w)
                mb_last[0] = time.time()
        with lock: st["calls"] += 1; st["mb"] += ep == MB
        try:
            req = urllib.request.Request(ep, data=json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params)).encode(),
                                         headers={"content-type": "application/json", "user-agent": "curl/8.5.0"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if "result" in r: return r["result"]
            if (r.get("error") or {}).get("code") in (-32015, -32009, -32007): return None    # unsupported / not available: no retry
        except Exception:
            pass
        with lock: st["err"] += 1
        time.sleep(0.6 * (a + 1))
    return "ERR"


def sigs(addr, smin):
    """publicnode first (its address index keeps ~23 h); mainnet-beta (full history, but it rate-limits hard) only to reach
    back past the creator's first watched launch when publicnode's list does not go that far"""
    out, before, complete = [], None, False
    for _ in range(4):
        p = dict(limit=1000)
        if before: p["before"] = before
        r = rpc(PN, "getSignaturesForAddress", [addr, p])
        if r == "ERR": break
        out += r
        if len(r) < 1000: complete = True; break
        before = r[-1]["signature"]
    used_mb = False
    if complete and (not out or out[-1]["slot"] >= smin):
        p = dict(limit=1000)
        if out: p["before"] = out[-1]["signature"]
        r = rpc(MB, "getSignaturesForAddress", [addr, p])
        if r == "ERR": return None, None
        out += r; used_mb = True; complete = len(r) < 1000
    if not out and not complete: return None, None
    return [(x["signature"], x["slot"], x.get("blockTime"), x.get("err") is not None) for x in out], (complete, used_mb)


def classify(tx, creator):
    m = tx["meta"]; logs = m.get("logMessages") or []
    keys = tx["transaction"]["message"]["accountKeys"]
    keys = keys + m.get("loadedAddresses", {}).get("writable", []) + m.get("loadedAddresses", {}).get("readonly", [])
    stack, ins = [], []                                         # instructions logged by the pump program itself
    for l in logs:
        if l.startswith("Program ") and " invoke [" in l: stack.append(l.split()[1])
        elif l.startswith("Program ") and (l.endswith(" success") or " failed" in l) and stack: stack.pop()
        elif l.startswith("Program log: Instruction: ") and stack and stack[-1] == PUMP: ins.append(l.split("Instruction: ")[1])
    pump = bool(ins)
    kind = "other"
    if pump:
        if any(i.startswith("Create") for i in ins): kind = "create"
        elif any(i.startswith("Sell") for i in ins): kind = "sell"
        elif any(i.startswith("Buy") for i in ins): kind = "buy"
    ci = keys.index(creator) if creator in keys else None
    pre = m["preBalances"][ci] if ci is not None else None; post = m["postBalances"][ci] if ci is not None else None
    tok = {}
    for b in m.get("preTokenBalances") or []:
        if b.get("owner") == creator: tok[b["mint"]] = tok.get(b["mint"], 0) - float(b["uiTokenAmount"]["uiAmount"] or 0)
    for b in m.get("postTokenBalances") or []:
        if b.get("owner") == creator: tok[b["mint"]] = tok.get(b["mint"], 0) + float(b["uiTokenAmount"]["uiAmount"] or 0)
    mints = sorted({b["mint"] for b in (m.get("postTokenBalances") or []) if b["mint"].endswith("pump") or kind == "create"})
    return dict(ins=ins[:3], kind=kind, pre=pre, post=post, tok={k: v for k, v in tok.items() if abs(v) > 0}, mints=mints[:3])


def gettx(sig):
    """publicnode only (keeps transactions ~40 h); mainnet-beta rate-limits too hard for thousands of calls"""
    p = [sig, dict(encoding="json", maxSupportedTransactionVersion=1)]
    r = rpc(PN, "getTransaction", p, tries=3)
    return (r if r not in ("ERR", None) else None), False


CL = json.load(open(INP))
try: res = json.load(open(OUT))
except Exception: res = {}


def one(creator):
    if creator in res or time.time() > DEADLINE: return
    Ss = sorted(CL[creator]); smin, smax = Ss[0], Ss[-1]
    wl, flags = sigs(creator, smin)
    if wl is None: return
    complete, older = flags
    cand = [s for s in wl if s[1] <= smax and not s[3]]        # newest first
    txs, ncre_old, nmb, trunc = [], 0, 0, False
    for i, (sig, slot, bt, _) in enumerate(cand):
        if ncre_old >= 11 and slot < smin: break
        if len(txs) >= MAXTX or nmb >= MAXMB or time.time() > DEADLINE: trunc = True; break
        tx, used_mb = gettx(sig); nmb += used_mb
        if tx is None:                                          # beyond publicnode's tx horizon: everything older is too
            txs.append(dict(slot=slot, bt=bt, kind="unknown")); trunc = True; break
        c = classify(tx, creator); c.update(slot=slot, bt=bt, sig=sig[:16]); txs.append(c)
        if c["kind"] == "create" and slot < smin: ncre_old += 1
    trunc = trunc or not complete
    with lock:
        res[creator] = dict(launches=Ss, nsig=len(wl), ncand=len(cand), complete=complete, older_from_mb=older, trunc=trunc,
                            oldest_slot=wl[-1][1] if wl else None, txs=txs)


# newest creators first (their history is inside publicnode's tx horizon), then by launch count
PRI = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else {}    # optional {creator: priority} (lower first)
todo = sorted([c for c in CL if c not in res], key=lambda c: (PRI.get(c, 9), -max(CL[c]), len(CL[c])))
print(f"creators {len(CL)}  todo {len(todo)}", flush=True)
t0 = time.time()
with cf.ThreadPoolExecutor(3) as ex:
    futs = [ex.submit(one, c) for c in todo]
    for i, f in enumerate(cf.as_completed(futs)):
        f.result()
        if i % 30 == 29:
            with lock: json.dump(res, open(OUT, "w"))
            print(f"{i + 1}/{len(todo)} done={len(res)} calls {st['calls']} mb {st['mb']} err {st['err']} {time.time() - t0:.0f}s", flush=True)
json.dump(res, open(OUT, "w"))
print(f"finished: {len(res)} creators, calls {st['calls']}, mb {st['mb']}, err {st['err']}, {time.time() - t0:.0f}s", flush=True)

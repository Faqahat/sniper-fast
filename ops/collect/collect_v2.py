#!/usr/bin/env python3
# READ-ONLY RAW COLLECTOR (no wallet, no sends, no filtering, no analysis). For HOURS it reads every confirmed block from
# Constant-K and records EVERY pump.fun create in the window and EVERY later transaction that touches one of those mints
# (bonding-curve trades, aggregator trades, transfers, burns, migration, PumpSwap trades), then follows them for TAIL_MIN
# more minutes. Enrichment workers add per launch: metadata JSON + socials + hosts, creator wallet history + funder,
# creator's earlier creates, Jito bundle of the create and of the earliest create-slot buys. Final pass: bonding-curve
# account + top holders of every mint. Everything is raw; analysis happens later and separately.
# Output dir: launches.jsonl, txs/*.jsonl.gz (5-min chunks), enrich.jsonl, final.jsonl, gaps.jsonl, status.json
import os, sys, json, time, gzip, base64, hashlib, threading, queue, urllib.request, urllib.error, urllib.parse, collections, traceback
from concurrent.futures import ThreadPoolExecutor

TOK = os.environ["CONSTANTK_TOKEN"]
URL = "https://rpc-frankfurt.constant-k.com/?api-key=" + TOK
OUT = os.environ.get("OUT", "/root/sniper-collect/run")
HOURS = float(os.environ.get("HOURS", "8")); TAIL_MIN = float(os.environ.get("TAIL_MIN", "60"))
LAG = int(os.environ.get("LAG", "32")); FETCH_THREADS = int(os.environ.get("FETCH_THREADS", "6"))
RPS = float(os.environ.get("RPS", "25"))
TIPMAP = json.load(open(os.environ.get("TIPMAP", "/root/sniper-collect/tipmap.json")))
os.makedirs(os.path.join(OUT, "txs"), exist_ok=True)
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; PUMPAMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
VOTE = "Vote111111111111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CREATE_DISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b

# ---------------- rate-limited RPC ----------------
_lk = threading.Lock(); _next = [0.0]
ST = collections.Counter()
def rpc(m, p, tries=10, timeout=90):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for i in range(tries):
        with _lk:
            t = max(time.time(), _next[0]); _next[0] = t + 1.0 / RPS
        d = t - time.time()
        if d > 0: time.sleep(d)
        ST["rpc_calls"] += 1
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=data, headers={"content-type": "application/json"}), timeout=timeout))
            if "error" in r:
                code = r["error"].get("code")
                if code in (-32007, -32009, -32004, -32001) and m == "getBlock": return {"_skip": code}
                ST["rpc_err"] += 1; time.sleep(min(30, 1 + 2 * i)); continue
            return r.get("result")
        except urllib.error.HTTPError as e:
            ST["rpc_429" if e.code == 429 else "rpc_http"] += 1; time.sleep(min(30, 2 + 3 * i))
        except Exception:
            ST["rpc_exc"] += 1; time.sleep(min(30, 1 + 2 * i))
    return None

# block reads: a pool of endpoints (env var names in BLOCK_EPS; URLs never printed), each with its own pace, with failover
BEPS = [os.environ[n] for n in os.environ.get("BLOCK_EPS", "SHYFT_RPC_URL,RMR_RPC_URL").split(",") if os.environ.get(n)] + [URL]
BRPS = float(os.environ.get("BLOCK_RPS", "6")); _bl = [threading.Lock() for _ in BEPS]; _bn = [0.0 for _ in BEPS]
def get_block(slot):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1,
                       "transactionDetails": "full", "rewards": False, "commitment": "confirmed"}]}).encode()
    n = len(BEPS)
    for k in range(4 * n):
        e = (slot + k) % n
        with _bl[e]:
            t = max(time.time(), _bn[e]); _bn[e] = t + 1.0 / BRPS
        d = t - time.time()
        if d > 0: time.sleep(d)
        ST[f"blk_ep{e}"] += 1
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(BEPS[e], data=data, headers={"content-type": "application/json"}), timeout=60))
            if "error" in r:
                if r["error"].get("code") in (-32007, -32009, -32004, -32001): return {"_skip": r["error"].get("code")}
                ST[f"blk_err{e}"] += 1; time.sleep(0.5 * (k // n + 1)); continue
            return r.get("result")
        except urllib.error.HTTPError as ex:
            ST[f"blk_http{ex.code}_ep{e}"] += 1; time.sleep(0.5 * (k // n + 1))
        except Exception:
            ST[f"blk_exc{e}"] += 1; time.sleep(0.5 * (k // n + 1))
    return None

def jlog(name, obj):
    with _wl:
        with open(os.path.join(OUT, name), "a") as f: f.write(json.dumps(obj, separators=(",", ":")) + "\n")
_wl = threading.Lock()

# ---------------- block parsing ----------------
TRACK = {}            # mint -> create slot (only mints created inside the window)
EARLY = {}            # mint -> earliest trade tx sigs in the create slot (for the Jito check)
_chunk = {"f": None, "t": 0, "n": 0}
def chunk_write(rec):
    now = time.time()
    if _chunk["f"] is None or now - _chunk["t"] > 300:
        if _chunk["f"]: _chunk["f"].close()
        _chunk["f"] = gzip.open(os.path.join(OUT, "txs", f"txs_{int(now)}.jsonl.gz"), "wt", compresslevel=3); _chunk["t"] = now
    _chunk["f"].write(json.dumps(rec, separators=(",", ":")) + "\n"); _chunk["n"] += 1

def parse_create(raw):
    o = 8; s = []
    for _ in range(3):
        n = int.from_bytes(raw[o:o + 4], "little"); s.append(raw[o + 4:o + 4 + n].decode("utf-8", "replace")); o += 4 + n
    k = lambda j: b58enc(raw[o + 32 * j:o + 32 * (j + 1)]) if len(raw) >= o + 32 * (j + 1) else None
    return dict(name=s[0], symbol=s[1], uri=s[2], mint=k(0), bonding_curve=k(1), user=k(2), creator=k(3))

def parse_trade(raw):
    u = lambda o: int.from_bytes(raw[o:o + 8], "little")
    return dict(mint=b58enc(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58enc(raw[57:89]), vsol=u(97), vtok=u(105))

def process_block(slot, b, in_window):
    bt = b.get("blockTime"); txs = b.get("transactions") or []
    nrec = 0
    for i, t in enumerate(txs):
        msg = t["transaction"]["message"]; meta = t.get("meta") or {}
        keys = msg["accountKeys"]
        if VOTE in keys: continue
        la = meta.get("loadedAddresses") or {}
        allk = keys + la.get("writable", []) + la.get("readonly", [])
        logs = meta.get("logMessages") or []
        evs = []; creates = []
        has_pump = PUMP in allk or PUMPAMM in allk
        if has_pump:
            for l in logs:
                if l.startswith("Program data: "):
                    s = l[14:].strip(); evs.append(s)
                    if in_window:
                        try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
                        except Exception: continue
                        if raw[:8] == CREATE_DISC:
                            try: creates.append(parse_create(raw))
                            except Exception: pass
        sig = t["transaction"]["signatures"][0]
        for c in creates:
            if c["mint"] and c["mint"] not in TRACK:
                TRACK[c["mint"]] = slot; EARLY[c["mint"]] = []; LCACHE[c["mint"]] = c
                c.update(slot=slot, idx=i, bt=bt, sig=sig, payer=keys[0], err=meta.get("err"), fee=meta.get("fee"),
                         ixn=[l[26:] for l in logs if l.startswith("Program log: Instruction: ")][:12])
                ST["launches"] += 1; jlog("launches.jsonl", c); EQ.put((time.time() + 25, c["mint"]))
        tb_m = {x.get("mint") for x in (meta.get("preTokenBalances") or []) + (meta.get("postTokenBalances") or [])}
        mints = [k for k in set(allk) | tb_m if k in TRACK]
        if not mints: continue
        nsig = msg["header"]["numRequiredSignatures"]
        pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
        sd = sorted(((allk[j], post[j] - pre[j]) for j in range(min(len(pre), len(post), len(allk))) if post[j] != pre[j]), key=lambda x: -abs(x[1]))
        tips = [[k, d] for k, d in sd if d > 0 and (k in TIPMAP or k.startswith("noz"))]
        cup = cul = None
        for ix in msg["instructions"]:
            if allk[ix["programIdIndex"]] == CB:
                try:
                    d = b58dec(ix["data"])
                    if d[:1] == b"\x03": cup = int.from_bytes(d[1:9], "little")
                    elif d[:1] == b"\x02": cul = int.from_bytes(d[1:5], "little")
                except Exception: pass
        progs = sorted({allk[ix["programIdIndex"]] for ix in msg["instructions"]} |
                       {allk[ix["programIdIndex"]] for inn in (meta.get("innerInstructions") or []) for ix in inn.get("instructions") or [] if ix["programIdIndex"] < len(allk)})
        tbal = {}
        for x in meta.get("preTokenBalances") or []:
            if x.get("mint") in TRACK: tbal[(x["accountIndex"])] = [x["mint"], x.get("owner"), int(x["uiTokenAmount"]["amount"]), 0]
        for x in meta.get("postTokenBalances") or []:
            if x.get("mint") in TRACK:
                r = tbal.setdefault(x["accountIndex"], [x["mint"], x.get("owner"), 0, 0]); r[3] = int(x["uiTokenAmount"]["amount"])
        rec = dict(s=slot, i=i, bt=bt, sig=sig, err=meta.get("err"), fee=meta.get("fee"), cu=meta.get("computeUnitsConsumed"), cup=cup, cul=cul,
                   signers=keys[:nsig], mints=mints, progs=progs, ixn=[l[26:] for l in logs if l.startswith("Program log: Instruction: ")][:16],
                   ev=evs[:12], tb=[v for v in tbal.values() if v[2] != v[3]], sd=sd[:14], tips=tips)
        chunk_write(rec); nrec += 1; ST["txs"] += 1
        # earliest create-slot trades per mint for the Jito bundle check
        if slot == TRACK.get(mints[0]) and len(EARLY.get(mints[0], [])) < 4 and not meta.get("err") and evs:
            EARLY[mints[0]].append([i, sig])
    return nrec

# ---------------- enrichment ----------------
EQ = queue.PriorityQueue(); _jl = threading.Lock(); _jlast = [0.0]
def jito(path):
    for i in range(5):
        with _jl:
            w = _jlast[0] + 0.15 - time.time()
            if w > 0: time.sleep(w)
            _jlast[0] = time.time()
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request("https://bundles.jito.wtf/api/v1/bundles/" + path, headers={"user-agent": "sniper-collect"}), timeout=20))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            ST["jito_err"] += 1; time.sleep(2 * (i + 1))
        except Exception:
            ST["jito_err"] += 1; time.sleep(2 * (i + 1))
    return "ERR"

def bundle_of(sig):
    j = jito("transaction/" + sig)
    if not (isinstance(j, list) and j): return None if j != "ERR" else "ERR"
    bid = j[0].get("bundle_id"); d = jito("bundle/" + bid)
    d = d[0] if isinstance(d, list) and d else {}
    return dict(bundle_id=bid, txs=d.get("txSignatures"), tippers=d.get("tippers"), tip=d.get("landedTipLamports"), validator=d.get("validator"), ts=d.get("timestamp"))

def fetch_uri(u):
    out = dict(uri=u)
    if not u: return out
    urls = [u]
    if "/ipfs/" in u:                                                  # ipfs.io 403s this server for many CIDs: fall back to other gateways
        cid = u.split("/ipfs/", 1)[1]
        urls += [g + cid for g in ("https://gateway.pinata.cloud/ipfs/", "https://w3s.link/ipfs/", "https://4everland.io/ipfs/", "https://ipfs.io/ipfs/") if g + cid != u]
    for x in urls:
        try:
            r = urllib.request.urlopen(urllib.request.Request(x, headers={"user-agent": "Mozilla/5.0"}), timeout=12)
            body = r.read(65536); out.update(status=r.status, ctype=r.headers.get("content-type"), host=urllib.parse.urlparse(x).hostname, fetched=x)
            try: out["json"] = json.loads(body)
            except Exception: out["text"] = body[:2000].decode("utf-8", "replace")
            return out
        except Exception as e:
            out["error"] = str(e)[:200]
    return out

LCACHE = {}
def enrich(mint):
    L = LCACHE.get(mint) or {}
    cre = L.get("creator") or L.get("user"); res = dict(mint=mint, t=time.time())
    try:
        res["meta"] = fetch_uri(L.get("uri"))
        j = (res["meta"].get("json") or {}) if isinstance(res["meta"].get("json"), dict) else {}
        hosts = {}
        for k in ("image", "website", "twitter", "telegram", "discord"):
            v = j.get(k) or (j.get("extensions") or {}).get(k) if isinstance(j.get("extensions"), dict) else j.get(k)
            if isinstance(v, str) and v: hosts[k] = urllib.parse.urlparse(v if "://" in v else "https://" + v).hostname
        res["hosts"] = hosts
    except Exception as e: res["meta_err"] = str(e)[:200]
    try:
        sigs = rpc("getSignaturesForAddress", [cre, {"limit": 100, "before": L.get("sig")}]) or []
        res["creator_prior_sigs"] = [[s["signature"], s["slot"], s.get("blockTime"), bool(s.get("err"))] for s in sigs]
        res["creator_prior_n"] = len(sigs)
        if sigs and len(sigs) < 100:                                   # whole visible history: the oldest tx is usually the funding transfer
            t = rpc("getTransaction", [sigs[-1]["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
            if t:
                k = t["transaction"]["message"]["accountKeys"]; m = t["meta"]
                d = [(k[j], m["postBalances"][j] - m["preBalances"][j]) for j in range(len(k))]
                src = min(d, key=lambda x: x[1]); res["funder"] = dict(sig=sigs[-1]["signature"], slot=t["slot"], from_=src[0], amount=-src[1], payer=k[0])
        prev = []
        for s in sigs[:8]:                                             # the creator's 8 most recent earlier txs: earlier pump creates?
            t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
            if not t: continue
            for l in (t["meta"] or {}).get("logMessages") or []:
                if l.startswith("Program data: "):
                    try: raw = base64.b64decode(l[14:].strip() + "=" * (-len(l[14:].strip()) % 4))
                    except Exception: continue
                    if raw[:8] == CREATE_DISC:
                        try: c = parse_create(raw); prev.append(dict(sig=s["signature"], slot=s["slot"], mint=c["mint"], name=c["name"], symbol=c["symbol"]))
                        except Exception: pass
        res["creator_recent_creates"] = prev
    except Exception as e: res["hist_err"] = str(e)[:200]
    try:
        res["jito_create"] = bundle_of(L.get("sig"))
        res["jito_early"] = [dict(idx=i, sig=s, bundle=bundle_of(s)) for i, s in EARLY.get(mint, [])[:3]]
    except Exception as e: res["jito_err"] = str(e)[:200]
    jlog("enrich.jsonl", res); ST["enriched"] += 1

def enrich_worker():
    while True:
        due, mint = EQ.get()
        if mint is None: return
        w = due - time.time()
        if w > 0: time.sleep(w)
        try: enrich(mint)
        except Exception: ST["enrich_exc"] += 1

# ---------------- main loop ----------------
def main():
    if os.environ.get("RESUME"):                       # continue an interrupted run in the same OUT dir (same window times)
        st = json.load(open(os.path.join(OUT, "run.json")))
        old = json.load(open(os.path.join(OUT, "status.json")))
        nxt = int(old.get("last_slot", st["start_slot"])) + 1
        done = set()
        if os.path.exists(os.path.join(OUT, "enrich.jsonl")):
            for l in open(os.path.join(OUT, "enrich.jsonl")):
                try: done.add(json.loads(l)["mint"])
                except Exception: pass
        for l in open(os.path.join(OUT, "launches.jsonl")):
            try: c = json.loads(l)
            except Exception: continue
            TRACK[c["mint"]] = c["slot"]; LCACHE[c["mint"]] = c; EARLY.setdefault(c["mint"], [])
            if c["mint"] not in done: EQ.put((time.time(), c["mint"]))
        ST.update({k: v for k, v in (old.get("stats") or {}).items() if isinstance(v, int)}); ST["resumes"] += 1
        st.setdefault("resumed_at", []).append([time.time(), nxt]); json.dump(st, open(os.path.join(OUT, "run.json"), "w"))
        t_end, t_tail = st["window_end_time"], st["tail_end_time"]
        print("resumed at slot", nxt, "tracked", len(TRACK), "to enrich", EQ.qsize(), flush=True)
    else:
        s0 = rpc("getSlot", [{"commitment": "confirmed"}]); t0 = time.time()
        t_end = t0 + HOURS * 3600; t_tail = t_end + TAIL_MIN * 60
        st = dict(start_slot=s0, start_time=t0, window_end_time=t_end, tail_end_time=t_tail, end_slot=None)
        json.dump(st, open(os.path.join(OUT, "run.json"), "w")); nxt = s0
    st["end_slot"] = None
    workers = [threading.Thread(target=enrich_worker, daemon=True) for _ in range(int(os.environ.get("ENRICH_WORKERS", "4")))]
    for w in workers: w.start()
    # window membership by BLOCK time (not wall clock), so a backlog never drops launches or truncates the tail
    win_end_bt = t_end; tail_end_bt = t_tail
    last_status = 0; cur = nxt; pending = collections.deque(); submit = nxt; AHEAD = int(os.environ.get("AHEAD", "40"))
    with ThreadPoolExecutor(FETCH_THREADS) as ex:
        while True:
            if (submit > cur - LAG and time.time() - st.get("_gs", 0) > 0.4) or time.time() - st.get("_gs", 0) > 5:
                st["_gs"] = time.time(); c = rpc("getSlot", [{"commitment": "confirmed"}])
                if isinstance(c, int): cur = c
            while len(pending) < AHEAD and submit <= cur - LAG and st["end_slot"] is None:
                pending.append((submit, ex.submit(get_block, submit))); submit += 1
            if not pending:
                if st["end_slot"] is not None: break
                time.sleep(0.3); continue
            sl, fut = pending[0]
            if not fut.done() and len(pending) < AHEAD and submit <= cur - LAG: continue
            b = fut.result(); pending.popleft()
            if b is None: ST["blocks_failed"] += 1; jlog("gaps.jsonl", dict(slot=sl, why="fetch failed"))
            elif "_skip" in b: ST["blocks_skipped"] += 1
            else:
                bt = b.get("blockTime") or time.time()
                if bt > tail_end_bt and st["end_slot"] is None: st["end_slot"] = sl
                try: process_block(sl, b, bt <= win_end_bt); ST["blocks_ok"] += 1
                except Exception as e: ST["blocks_parse_err"] += 1; jlog("gaps.jsonl", dict(slot=sl, why="parse " + repr(e)[:200]))
                st["last_slot"] = sl; st["last_block_time"] = bt
            if time.time() - last_status > 30:
                last_status = time.time()
                s = dict(st, now=time.time(), confirmed_slot=cur, lag_slots=cur - st.get("last_slot", nxt),
                         phase=("window" if st.get("last_block_time", 0) <= win_end_bt else "tail"),
                         tracked_mints=len(TRACK), enrich_queue=EQ.qsize(), chunk_records=_chunk["n"], stats=dict(ST))
                json.dump(s, open(os.path.join(OUT, "status.json.tmp"), "w")); os.replace(os.path.join(OUT, "status.json.tmp"), os.path.join(OUT, "status.json"))
    if _chunk["f"]: _chunk["f"].close()
    # final pass: drain enrichment, then bonding-curve account + top holders for every mint
    json.dump(dict(st, phase="enrich-drain", stats=dict(ST)), open(os.path.join(OUT, "status.json"), "w"))
    while not EQ.empty(): time.sleep(5)
    for _ in workers: EQ.put((0, None))
    for w in workers: w.join(timeout=600)
    mints = list(TRACK)
    curves = {m: LCACHE.get(m, {}).get("bonding_curve") for m in mints}
    for k in range(0, len(mints), 100):
        part = mints[k:k + 100]
        acc = rpc("getMultipleAccounts", [[curves[m] for m in part if curves[m]], {"encoding": "base64"}]) or {}
        vals = iter((acc or {}).get("value") or [])
        for m in part:
            if not curves[m]: continue
            a = next(vals, None)
            hold = rpc("getTokenLargestAccounts", [m])
            jlog("final.jsonl", dict(mint=m, t=time.time(), curve=a, top_holders=(hold or {}).get("value")))
        json.dump(dict(st, phase=f"final {k + len(part)}/{len(mints)}", stats=dict(ST)), open(os.path.join(OUT, "status.json"), "w"))
    json.dump(dict(st, phase="DONE", now=time.time(), tracked_mints=len(TRACK), stats=dict(ST)), open(os.path.join(OUT, "status.json"), "w"))
    print("DONE", flush=True)

if __name__ == "__main__":
    try: main()
    except Exception:
        traceback.print_exc(); raise

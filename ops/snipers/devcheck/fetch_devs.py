#!/usr/bin/env python3
# READ-ONLY: for every pump.fun token a wallet bought (first buy in its ledger), get the creator (TradeEvent of that buy)
# and the create slot (oldest signature on the mint before that buy). Resumable: raw buy txs -> <cache>/, sig lists -> <cache>_sigs/.
# usage: RPC_URL_FILE=~/.config/sniper/ck_rpc_url python3 -I fetch_devs.py <ledger.json> <cachedir> <out.json>
import sys, os, json, time, base64, threading, urllib.request, concurrent.futures as cf
LED, CACHE, OUT = sys.argv[1:4]; SIGC = CACHE.rstrip("/") + "_sigs"
os.makedirs(CACHE, exist_ok=True); os.makedirs(SIGC, exist_ok=True)
CK = open(os.path.expanduser(os.environ.get("RPC_URL_FILE", "~/.config/sniper/ck_rpc_url"))).read().strip(); PUB = "https://api.mainnet-beta.solana.com"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); import hashlib; CD = hashlib.sha256(b"event:CreateEvent").digest()[:8]
CRC = CACHE.rstrip("/") + "_create"; os.makedirs(CRC, exist_ok=True)
def create_event(tx, m):
    for l in ((tx or {}).get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != CD: continue
        o = 8
        for _ in range(3): n = int.from_bytes(raw[o:o + 4], "little"); o += 4 + n
        if b58(raw[o:o + 32]) != m: continue
        return dict(user=b58(raw[o + 64:o + 96]), creator=b58(raw[o + 96:o + 128]))
    return None
lock = threading.Lock(); last = [0.0]
def rpc(ep, m, p, tries=8):
    for i in range(tries):
        if ep == PUB:
            with lock:
                w = last[0] + 1.0 - time.time()
                if w > 0: time.sleep(w)
                last[0] = time.time()
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=30))
            if "error" in r: raise RuntimeError(str(r["error"])[:200])
            return r["result"]
        except Exception as e:
            err = e; time.sleep(min(8, 0.5 * 2 ** i))
    raise RuntimeError(f"{m} failed: {err}")
MIN = rpc(CK, "minimumLedgerSlot", []) + 60000
D = json.load(open(LED)); W = D["wallet"]
first = {}
if len(sys.argv) > 4: first = json.load(open(sys.argv[4]))  # failed attempts {mint: {sig, slot, bt}} instead of bought tokens
for x in ([] if first else sorted([x for x in D["txs"] if not x.get("missing") and not x.get("err")], key=lambda x: x["slot"])):
    for t in x["trades"]:
        if t["buy"] and t["mint"] not in first: first[t["mint"]] = x
print(f"{W[:8]}: {len(first)} pump.fun tokens bought; CK history from slot {MIN}", flush=True)
def one(item):
    m, x = item; ep = CK if x["slot"] > MIN else PUB
    p = os.path.join(CACHE, x["sig"] + ".json")
    if os.path.exists(p): tx = json.load(open(p))
    else:
        tx = rpc(ep, "getTransaction", [x["sig"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if tx: json.dump(tx, open(p, "w"))
    creator = None; vsol = None
    for l in ((tx or {}).get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 209 and b58(raw[8:40]) == m and b58(raw[57:89]) == W:
            creator = b58(raw[177:209]); vsol = int.from_bytes(raw[97:105], "little") / 1e9; sol = int.from_bytes(raw[40:48], "little") / 1e9; break
    q = os.path.join(SIGC, m + ".json")
    if os.path.exists(q): sigs = json.load(open(q))
    else:
        sigs = rpc(ep, "getSignaturesForAddress", [m, {"before": x["sig"], "limit": 1000, "commitment": "confirmed"}])
        json.dump(sigs, open(q, "w"))
    ok = [s for s in sigs if s.get("err") is None]
    ce = None; payer = None
    if sigs and len(sigs) < 1000:
        cp = os.path.join(CRC, sigs[-1]["signature"] + ".json")
        if os.path.exists(cp): ctx = json.load(open(cp))
        else:
            ctx = rpc(ep, "getTransaction", [sigs[-1]["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
            if ctx: json.dump(ctx, open(cp, "w"))
        ce = create_event(ctx, m)
        try: payer = ctx["transaction"]["message"]["accountKeys"][0]["pubkey"]
        except Exception: pass
    cs = sigs[-1]["slot"] if sigs and len(sigs) < 1000 else None
    return m, dict(signer=(ce or {}).get("user"), creator_field=(ce or {}).get("creator"), payer=payer, creator=creator, buy_sig=x["sig"], buy_slot=x["slot"], bt=x["bt"], create_slot=cs, delta=(x["slot"] - cs) if cs is not None else None,
                   n_before=len(sigs), n_before_ok=len(ok), in_create_slot=sum(1 for s in ok if cs is not None and s["slot"] == cs),
                   curve_sol_before=(round(vsol - 30 - sol, 3) if vsol else None))
res = json.load(open(OUT)) if os.path.exists(OUT) else {}
res = {m: r for m, r in res.items() if "signer" in r}
todo = [(m, x) for m, x in first.items() if m not in res]
recent = [i for i in todo if i[1]["slot"] > MIN]; old = [] if os.environ.get("CK_ONLY") else [i for i in todo if i[1]["slot"] <= MIN]
print(f"   to do {len(todo)} (owner RPC {len(recent)}, public {len(old)})", flush=True)
def run(items, n):
    done = 0
    with cf.ThreadPoolExecutor(n) as ex:
        for f in cf.as_completed([ex.submit(one, i) for i in items]):
            try: m, r = f.result(); res[m] = r
            except Exception as e: print("   fail:", str(e)[:150], flush=True)
            done += 1
            if done % 100 == 0:
                json.dump(res, open(OUT, "w")); print(f"   {done}/{len(items)}", flush=True)
run(recent, 8); json.dump(res, open(OUT, "w")); run(old, 1); json.dump(res, open(OUT, "w"))
print(f"   saved {len(res)} / {len(first)}; creator missing {sum(1 for r in res.values() if not r['creator'])}; create slot unknown (>=1000 txs before) {sum(1 for r in res.values() if r['create_slot'] is None)}", flush=True)

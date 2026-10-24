#!/usr/bin/env python3
# How fast did OUR past buys land? READ-ONLY RPC (owner's endpoint, never printed). For each wallet: its recent successful
# pump.fun buys; for each buy the token's create tx; both positioned in their blocks (getBlock signatures, votes included =
# the same index the collector and the replay use). Delay after the create in slots and in the replay's block-position ms
# (slot x 212 ms + index / block size x 212 ms), the txs that landed between the create and us, and what we paid: priority
# fee, tips and the landing services they went to (collector tip map), and the leader's client.
# usage: python3 -I our_speed.py WALLET:LABEL:N [WALLET:LABEL:N ...]   (N = how many of the most recent buys)
import sys, os, json, time, base64, collections, statistics, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); SLOT_MS = 212.0
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def rpc(m, p, tries=6):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
    return None
BLK = {}
def block(slot):
    if slot not in BLK:
        b = rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False, "commitment": "confirmed"}])
        BLK[slot] = b["signatures"] if b else None
    return BLK[slot]
def pos(slot, sig):
    sigs = block(slot)
    if not sigs or sig not in sigs: return None
    return sigs.index(sig), len(sigs)
def analyze_tx(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t or t["meta"]["err"] is not None: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    ev = None
    for l in t["meta"].get("logMessages") or []:
        if l.startswith("Program data: "):
            x = l[14:].split()[0]; x += "=" * (-len(x) % 4)
            try: raw = base64.b64decode(x)
            except Exception: continue
            if raw[:8] == TD and len(raw) >= 113: ev = dict(mint=b58enc(raw[8:40]), sol=int.from_bytes(raw[40:48], "little"), buy=raw[56] == 1); break
    if not ev or not ev["buy"]: return None
    cu_price = cu_limit = None; tips = []
    for ix in msg["instructions"]:
        p = keys[ix["programIdIndex"]]; d = b58dec(ix["data"])
        if p == CB and d:
            if d[0] == 3: cu_price = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cu_limit = int.from_bytes(d[1:5], "little")
        elif p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
            to = keys[ix["accounts"][1]]
            if to in TIP: tips.append((TIP[to], int.from_bytes(d[4:12], "little")))
    return dict(sig=sig, slot=t["slot"], bt=t.get("blockTime"), mint=ev["mint"], sol=ev["sol"], fee=t["meta"]["fee"], cu_price=cu_price, cu_limit=cu_limit,
                cu_used=t["meta"].get("computeUnitsConsumed"), tips=tips, top_pump=any(keys[ix["programIdIndex"]] == PUMP for ix in msg["instructions"]))
def create_of(mint, before):
    # oldest tx of the mint before our buy = its create (snipes buy within a few slots, so one page is enough)
    page = rpc("getSignaturesForAddress", [mint, {"before": before, "limit": 1000}]) or []
    if not page: return None
    oldest = page[-1]
    return dict(sig=oldest["signature"], slot=oldest["slot"], n_before=len(page))
LEAD = {}
def leader_client(slot):
    ep = slot // 432000 * 432000
    if ep not in LEAD:
        sched = rpc("getLeaderSchedule", [slot]) or {}
        LEAD[ep] = {ep + i: ident for ident, idxs in sched.items() for i in idxs}
        if "nodes" not in LEAD:
            from_nodes = rpc("getClusterNodes", []) or []
            LEAD["nodes"] = {n["pubkey"]: (n.get("clientId") or "", n.get("version") or "") for n in from_nodes}
    ident = LEAD[ep].get(slot)
    c, ver = LEAD["nodes"].get(ident, ("", ""))
    if "Bam" in c or "BAM" in c: return "bam"
    if "Harmonic" in c: return "harmonic"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    return c or ("?" if not ver else ver)
def run(wallet, label, n):
    sigs = []; before = None
    while len(sigs) < 1000:
        page = rpc("getSignaturesForAddress", [wallet, {"limit": 1000, **({"before": before} if before else {})}]) or []
        if not page: break
        sigs += [p["signature"] for p in page if p.get("err") is None]; before = page[-1]["signature"]
        if len(page) < 1000: break
    buys = []
    with cf.ThreadPoolExecutor(12) as ex:
        for r in ex.map(analyze_tx, sigs[:600]):
            if r: buys.append(r)
            if len(buys) >= n: break
    buys = sorted(buys, key=lambda r: r["slot"], reverse=True)[:n]
    out = []
    for b in buys:
        c = create_of(b["mint"], b["sig"])
        if not c: continue
        pb = pos(b["slot"], b["sig"]); pc = pos(c["slot"], c["sig"])
        if not pb or not pc: continue
        ms = (b["slot"] - c["slot"]) * SLOT_MS + (pb[0] / pb[1] - pc[0] / pc[1]) * SLOT_MS
        ahead = None
        if b["slot"] == c["slot"]: ahead = pb[0] - pc[0] - 1
        out.append(dict(b, label=label, create_sig=c["sig"], create_slot=c["slot"], dslot=b["slot"] - c["slot"], ms=round(ms, 1),
                        idx=pb[0], size=pb[1], cidx=pc[0], ahead_same_slot=ahead, txs_before_us_on_mint=c["n_before"], client=leader_client(b["slot"])))
    return out
if __name__ == "__main__":
    allr = []
    for a in sys.argv[1:]:
        w, label, n = a.split(":"); allr += run(w, label, int(n))
    json.dump(allr, open("/home/moiz/sniper/ops/speedcheck/our_speed.json", "w"), indent=1)
    for label in dict.fromkeys(r["label"] for r in allr):
        v = [r for r in allr if r["label"] == label]
        print(f"\n== {label}: {len(v)} buys")
        for r in v:
            prio = (r["cu_price"] or 0) * (r["cu_limit"] or 0) / 1e15
            tips = ", ".join(f"{s} {x / 1e9:.4f}" for s, x in r["tips"]) or "none"
            prio = f"{prio:.5f} (tx fee {r['fee'] / 1e9:.5f})"
            print(f"  {time.strftime('%m-%d %H:%M', time.gmtime((r['bt'] or 0) + 18000))} PKT {r['mint'][:6]} buy {r['sol'] / 1e9:.3f} SOL | create→us {r['dslot']} slot(s), "
                  f"{r['ms']:6.1f} ms | idx {r['idx']}/{r['size']} | ahead in slot {r['ahead_same_slot']} | prio {prio} SOL, tips [{tips}] | leader {r['client']}")
        ms = [r["ms"] for r in v]
        if ms: print(f"  median {statistics.median(ms):.1f} ms, min {min(ms):.1f}, max {max(ms):.1f}; same slot as the create {sum(1 for r in v if r['dslot'] == 0)}/{len(v)}")

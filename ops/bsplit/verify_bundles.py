# READ-ONLY double-check on OUR blacklist paper trades: are the buys glued right behind the create really in the
# creator's Jito bundle? Fresh queries to the public Jito explorer for the create tx AND the first glued buy.
import sys, json, time, urllib.request, collections as C, concurrent.futures as cf
sys.path.insert(0, "/root/indep")
from common import get_block, is_vote, events, tx_summary, load_tipmap, rpc

tipmap = load_tipmap()
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
L = []
for f in ["/root/bsplit/out.jsonl", "/root/bsplit/out_bl82.jsonl"]:
    for l in open(f):
        r = json.loads(l)
        if r.get("glued", 0) >= 1:
            L.append(r)
print("glued launches:", len(L), flush=True)


def blockinfo(r):
    blk = get_block(r["slot"])
    ld = rpc("getSlotLeaders", [r["slot"], 1])
    leader = ld[0] if isinstance(ld, list) and ld else None
    r["client"] = nodes.get(leader, {}).get("clientId", "?") if leader else "?"
    if not isinstance(blk, dict) or "transactions" not in blk:
        return r
    txs = blk["transactions"]
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        if meta.get("err") is not None:
            continue
        tr, cr = events(meta.get("logMessages"))
        if any(c["mint"] == r["mint"] for c in cr):
            cs = tx_summary(t, tipmap)[0]
            r["create_sig"], r["create_signers"] = cs["sig"], cs["signers"]
            r["create_tips"] = cs["tips"]
            gl = []
            for t2 in txs[i + 1:]:
                if is_vote(t2):
                    continue
                m2 = t2.get("meta") or {}
                tr2, _ = events(m2.get("logMessages"))
                ev = [e for e in tr2 if e["mint"] == r["mint"] and e["buy"]]
                if not ev or m2.get("err") is not None:
                    break
                s2 = tx_summary(t2, tipmap)[0]
                gl.append({"sig": s2["sig"], "payer": s2["payer"], "sol": sum(e["sol"] for e in ev) / 1e9, "tips": s2["tips"],
                           "prio": (s2["fee"] or 0) - 5000 * len(s2["signers"])})
            r["glued_txs"] = gl
            break
    return r


with cf.ThreadPoolExecutor(max_workers=8) as ex:
    L = list(ex.map(blockinfo, L))
print("blocks done", flush=True)


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "research"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def bundle_of(sig):
    a = get(f"https://bundles.jito.wtf/api/v1/bundles/transaction/{sig}")
    time.sleep(0.6)
    if a is None:
        return None
    if not (isinstance(a, list) and a):
        return {"in": False}
    bid = a[0].get("bundle_id")
    b = get(f"https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}")
    time.sleep(0.6)
    if isinstance(b, list) and b:
        b = b[0]
    txs = (b.get("txSignatures") or b.get("transactions") or []) if isinstance(b, dict) else []
    return {"in": True, "id": bid, "txs": txs}


out = open("/root/bsplit/verify.jsonl", "w")
for k, r in enumerate(L):
    if "create_sig" not in r:
        continue
    cb = bundle_of(r["create_sig"])
    r["create_bundle"] = cb
    g = r.get("glued_txs") or []
    if cb and cb.get("in"):
        for x in g:
            x["in_create_bundle"] = x["sig"] in cb["txs"]
    elif g:
        fb = bundle_of(g[0]["sig"])        # maybe the buy rode a separate bundle
        r["first_glued_bundle"] = fb
    out.write(json.dumps({k2: v for k2, v in r.items() if k2 != "path"}) + "\n")
    out.flush()
    if k % 25 == 0:
        print(k, "/", len(L), flush=True)
print("VERIFY_DONE", flush=True)

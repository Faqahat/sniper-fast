# READ-ONLY: peaks of given mints vs the price right behind the creator's bundle (our realistic entry).
import sys, json, concurrent.futures as cf
sys.path.insert(0, "/root/indep")
from common import rpc, events, get_block, is_vote
MINTS = [(int(a), b) for a, b in (x.split(":") for x in sys.argv[1:])]


def tx(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not isinstance(t, dict) or "meta" not in t:
        return None
    tr, _ = events(t["meta"].get("logMessages"))
    return t.get("blockTime"), t["slot"], tr


def entry_and_name(slot, mint):
    b = get_block(slot)
    txs = [t for t in b.get("transactions", []) if not is_vote(t)] if isinstance(b, dict) else []
    for i, t in enumerate(txs):
        tr, cr = events((t.get("meta") or {}).get("logMessages"))
        c = [x for x in cr if x["mint"] == mint]
        if not c:
            continue
        last = [e for e in tr if e["mint"] == mint]
        p = (last[-1]["vsol"] / last[-1]["vtok"]) if last else None
        for t2 in txs[i + 1:]:
            tr2, _ = events((t2.get("meta") or {}).get("logMessages"))
            ev = [e for e in tr2 if e["mint"] == mint and e["buy"]]
            if (t2.get("meta") or {}).get("err") is None and ev:
                p = ev[-1]["vsol"] / ev[-1]["vtok"]
            else:
                break
        return p, c[0]["name"], b.get("blockTime")
    return None, "?", None


print(f"{'name':24} {'peak30s':>8} {'peak1m':>8} {'peak10m':>8} {'now':>8} {'txs':>6}  (x price right behind the bundle)")
for slot, mint in MINTS:
    e, name, t0 = entry_and_name(slot, mint)
    if not e:
        print(f"{name[:24]:24} entry not found")
        continue
    sigs, before = [], None
    for _ in range(30):
        p = {"limit": 1000}
        if before:
            p["before"] = before
        r = rpc("getSignaturesForAddress", [mint, p])
        if not isinstance(r, list) or not r:
            break
        sigs += r
        before = r[-1]["signature"]
        if len(r) < 1000:
            break
    win = [s for s in sigs if s.get("err") is None and s.get("blockTime") and s["blockTime"] <= t0 + 600]
    pts = []
    with cf.ThreadPoolExecutor(6) as ex:
        for r in ex.map(lambda s: tx(s["signature"]), win[-1500:]):
            if r:
                for ev in r[2]:
                    if ev["mint"] == mint and ev["vtok"]:
                        pts.append((r[0], ev["vsol"] / ev["vtok"]))
    latest = None
    if sigs:
        r = tx(sigs[0]["signature"])
        ee = [x for x in (r[2] if r else []) if x["mint"] == mint and x["vtok"]]
        latest = ee[-1]["vsol"] / ee[-1]["vtok"] if ee else None
    pk = lambda sec: max([p for bt, p in pts if t0 <= bt <= t0 + sec] or [0]) / e
    print(f"{name[:24]:24} {pk(30):8.2f} {pk(60):8.2f} {pk(600):8.2f} {((latest or 0) / e):8.2f} {len(sigs):6}")

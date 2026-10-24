# READ-ONLY: what happened to each token a run fired on? For every FIRE in the log: post-bundle price (our entry
# reference), the price ~3 slots after the create slot (our ~650 ms exit), peak/low within 30 s and 60 s, and whether
# the dev / creator-bundle wallets sold in the first 60 s (rug signal). Prices are x the post-bundle price.
# usage: python3 fire_outcomes.py <engine log>
import sys, re, json
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc, get_block, events, is_vote
SLOT_S = 0.217
txt = open(sys.argv[1], errors="replace").read()
fires = list(dict.fromkeys(re.findall(r"^\s*FIRE slot=(\d+) mint=(\w+)", txt, re.M)))


def tx(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not isinstance(t, dict) or "meta" not in t: return None
    tr, _ = events(t["meta"].get("logMessages"))
    return t["slot"], t.get("blockTime"), tr


def one(item):
    S, m = int(item[0]), item[1]
    b = get_block(S)
    txs = [t for t in b["transactions"] if not is_vote(t)]
    ci = None; creator = set(); pb = None; dev_sol = 0; bundle_sol = 0
    for i, t in enumerate(txs):
        tr, cr = events((t.get("meta") or {}).get("logMessages"))
        if ci is None:
            c = [x for x in cr if x["mint"] == m]
            if c:
                ci = i
                creator |= set(t["transaction"]["message"]["accountKeys"][: t["transaction"]["message"]["header"]["numRequiredSignatures"]])
                ev = [e for e in tr if e["mint"] == m and e["buy"]]
                dev_sol = sum(e["sol"] for e in ev) / 1e9
                if ev: pb = ev[-1]["vsol"] / ev[-1]["vtok"]
            continue
        ev = [e for e in tr if e["mint"] == m and e["buy"]]
        if ev and (t.get("meta") or {}).get("err") is None and i == ci + 1 + len(creator) - len(creator):  # glued run
            pass
    # glued bundle: consecutive successful buys right after the create
    j = ci + 1
    while j < len(txs):
        t = txs[j]; tr, _ = events((t.get("meta") or {}).get("logMessages"))
        ev = [e for e in tr if e["mint"] == m and e["buy"]]
        if not ev or (t.get("meta") or {}).get("err") is not None: break
        bundle_sol += sum(e["sol"] for e in ev) / 1e9; pb = ev[-1]["vsol"] / ev[-1]["vtok"]
        creator |= {e["user"] for e in ev}; j += 1
    sigs, before = [], None
    for _ in range(10):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [m, p])
        if not isinstance(r, list) or not r: break
        sigs += r; before = r[-1]["signature"]
        if len(r) < 1000: break
    win = [s for s in sigs if s.get("err") is None and s["slot"] <= S + int(60 / SLOT_S)]
    pts = []; dev_sells = []
    with ThreadPoolExecutor(6) as ex:
        for r in ex.map(lambda s: tx(s["signature"]), win[-1500:]):
            if not r: continue
            for e in r[2]:
                if e["mint"] != m or not e["vtok"]: continue
                pts.append((r[0], e["vsol"] / e["vtok"]))
                if not e["buy"] and e["user"] in creator: dev_sells.append((r[0] - S, e["sol"] / 1e9))
    pts.sort()
    def at(slot):
        v = [p for s, p in pts if s <= slot]
        return (v[-1] / pb) if v else None
    def pk(sec):
        v = [p for s, p in pts if s <= S + int(sec / SLOT_S)]
        return (max(v) / pb, min(v) / pb) if v else (None, None)
    first_dump = min(dev_sells)[0] if dev_sells else None
    return dict(mint=m, S=S, dev=dev_sol, bundle=bundle_sol, exit3=at(S + 3), p30=pk(30), p60=pk(60), last=at(S + int(60 / SLOT_S)),
                dev_sold=sum(s for _, s in dev_sells), first_dump_s=(first_dump * SLOT_S if first_dump is not None else None), ntx=len(sigs))


rows = [one(f) for f in fires]
print(f"{len(rows)} fired tokens  (prices = x the post-bundle price, i.e. our reference entry)")
print(f"{'mint':10} {'dev':>5} {'bundle':>6} {'@~650ms':>8} {'peak30s':>8} {'low30s':>7} {'peak60s':>8} {'@60s':>6} {'dev+bundle sold':>16} {'first dump':>10} {'txs':>5}")
for r in rows:
    f = lambda x: "-" if x is None else f"{x:.2f}"
    dump = "-" if r["first_dump_s"] is None else f"{r['first_dump_s']:.1f} s"
    print(f"{r['mint'][:10]} {r['dev']:5.2f} {r['bundle']:6.2f} {f(r['exit3']):>8} {f(r['p30'][0]):>8} {f(r['p30'][1]):>7} {f(r['p60'][0]):>8} {f(r['last']):>6} {r['dev_sold']:13.2f} SOL {dump:>10} {r['ntx']:5}")

#!/usr/bin/env python3
# Who uses Soyas on Jito-client leaders? (local collector raw txs of run R3 = 10-23 19:26 PKT -> now + read-only RPC for the leader
# schedule / client ids). Top bots = the 462 profitable-cohort wallets (TRAIN census) + HkQ7hMjy / haqqiUUX / DYXDDrZC.
# Per landed pump BUY of a top bot: the slot leader's client and the landing services its tips paid (collector tip map).
import os, sys, json, gzip, glob, base64, urllib.request, collections
from multiprocessing import Pool
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p): return json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=120)).get("result")
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
TOP = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json"))) | {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw"}
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def work(f):
    out = []
    try:
        for line in gzip.open(f, "rt"):
            if PUMP not in line or '"err":null' not in line: continue
            r = json.loads(line); sg = (r.get("signers") or [None])[0]
            if sg not in TOP: continue
            buy = None
            for e in r.get("ev") or []:
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except Exception: continue
                if raw[:8] == TD and len(raw) >= 113 and b58(raw[57:89]) == sg: buy = raw[56] == 1; break
            if not buy: continue
            svc = sorted({TIP.get(a, "other-tip") for a, _ in (r.get("tips") or [])}) or ["no tip"]
            out.append((sg, r["s"], "+".join(svc)))
    except (EOFError, OSError): pass
    return out
if __name__ == "__main__":
    files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261023_1426/txs/*.jsonl.gz"))
    rows = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, files): rows += o
    es = rpc("getEpochSchedule", []); sched = {}
    for s in sorted({r[1] for r in rows})[::20000] + [max(r[1] for r in rows)]:
        ep = (s - es["firstNormalSlot"]) // es["slotsPerEpoch"]
        if ep not in sched:
            first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]; sc = rpc("getLeaderSchedule", [s]) or {}; sched[ep] = {first + i: k for k, v in sc.items() for i in v}
    lead = {}
    for v in sched.values(): lead.update(v)
    nodes = {n["pubkey"]: (n.get("clientId") or "") for n in rpc("getClusterNodes", [])}
    def cl(c): return "BAM" if "Bam" in c or "BAM" in c else ("Harmonic" if "Harmonic" in c else ("Jito" if c in ("JitoLabs", "Rakurai") else ("Firedancer" if "dancer" in c.lower() else (c or "?"))))
    R = [(w, cl(nodes.get(lead.get(s), "")), svc) for w, s, svc in rows]
    json.dump(R, open("/home/moiz/sniper/ops/overnight/soyas/soyas_usage.json", "w"))
    jito = [x for x in R if x[1] == "Jito"]; uses = lambda x: "soyas" in x[2].split("+")
    print(f"top-bot BUYS landed in R3: {len(R)} ({len({x[0] for x in R})} bots); on Jito-client leaders: {len(jito)} ({len({x[0] for x in jito})} bots)")
    print(f"buys on Jito leaders carrying a Soyas tip: {sum(1 for x in jito if uses(x))} ({sum(1 for x in jito if uses(x)) / max(len(jito), 1):.1%}) | on other clients: "
          + ", ".join(f"{c} {sum(1 for x in R if x[1] == c and uses(x)) / max(sum(1 for x in R if x[1] == c), 1):.1%}" for c in ("BAM", "Harmonic", "Firedancer")))
    per = collections.defaultdict(lambda: [0, 0])
    for x in jito: per[x[0]][0] += 1; per[x[0]][1] += uses(x)
    users = {w: v for w, v in per.items() if v[1] > 0}
    print(f"bots with >= 1 Soyas-tipped buy on Jito leaders: {len(users)} of {len(per)}; with >= 20 Jito-leader buys: {sum(1 for v in per.values() if v[0] >= 20)} bots, of which use Soyas there: {sum(1 for v in per.values() if v[0] >= 20 and v[1] > 0)}")
    for w, (n, s) in sorted(users.items(), key=lambda kv: -kv[1][1])[:15]:
        print(f"   {w[:8]}  Jito-leader buys {n:4d}  with Soyas {s:4d} ({s / n:.0%})")
    svc = collections.Counter(s for x in jito for s in x[2].split("+"))
    print("services on top-bot buys at Jito leaders (share of buys carrying each):", ", ".join(f"{k} {v / len(jito):.0%}" for k, v in svc.most_common(12)))

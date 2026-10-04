#!/usr/bin/env python3
"""Fingerprint competitors' send paths from their own transactions (wins AND failures): every SOL transfer instruction
(top-level and inner) by destination, classified by known sender tip lists (a failed tx keeps its instructions, so the
INTENDED sender shows even when the tip reverted); durable-nonce use; fees; and where they land: the leader of each
landed slot and its distance from Cherry, against the base rate of all leaders. Read-only RPC + ping.
usage: paths.py <N per competitor> [extra_tips.json]   (competitors: top takers in who.jsonl + takers*.jsonl)"""
import json, glob, subprocess, collections, concurrent.futures as cf, types, sys, time
_ns = {}
exec(open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/"')[0], _ns)
T = types.SimpleNamespace(**_ns)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None
SYS = "11111111111111111111111111111111"

# known tip lists: service -> addresses
KNOWN = {
    "jito": "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5 HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49 DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL 3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    "helius": "4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ 9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta 5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn 2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD 2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF 3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT 4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey 4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or",
}
for k in T.TIPS:
    if k.lower().startswith("astra") or k[:4] in ("Ax2J", "ASdX"): KNOWN.setdefault("astralane", ""); KNOWN["astralane"] += " " + k
    elif k.startswith("moon"): KNOWN.setdefault("lunar", ""); KNOWN["lunar"] += " " + k
    elif k[:2] in [f"t{i}" for i in range(1, 10)] and len(k) < 45: KNOWN.setdefault("bolt", ""); KNOWN["bolt"] += " " + k
if len(sys.argv) > 2 and sys.argv[2]:
    for name, addrs in json.load(open(sys.argv[2])).items(): KNOWN[name] = " ".join(addrs)
SERVICE = {a: n for n, l in KNOWN.items() for a in l.split()}

# competitors: the most frequent takers we recorded
cnt = collections.Counter()
for f in ["/root/arb-lab/runs/who.jsonl"]:
    for x in map(json.loads, open(f)):
        if x["ok"] and x["signer_sol_wsol_change"] > 0: cnt[x["signer"]] += 1
for f in glob.glob("/root/arb-lab/runs/takers*.jsonl"):
    for r in map(json.loads, open(f)):
        for k in r["takers"][:1]: cnt[k["signer"]] += 1
COMP = [s for s, n in cnt.most_common(int(sys.argv[3]) if len(sys.argv) > 3 else 8)]

nodes = T.rpc("getClusterNodes", [])
ip = {n["pubkey"]: (n.get("gossip") or "").split(":")[0] for n in nodes} if isinstance(nodes, list) else {}
_rtt = {}
def ping(h):
    if not h: return None
    try:
        out = subprocess.run(["ping", "-c", "2", "-i", "0.2", "-W", "1", "-q", h], capture_output=True, text=True, timeout=5).stdout
        line = [l for l in out.splitlines() if "min/avg" in l]
        return float(line[0].split("=")[1].split("/")[0]) if line else None
    except Exception: return None

unknown = collections.Counter()
report = {}
summary = []
for who in COMP:
    sigs = T.rpc("getSignaturesForAddress", [who, {"limit": N}])
    if not isinstance(sigs, list): continue
    rows = []
    for s in sigs:
        tx = T.rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        time.sleep(0.02)
        if not tx or "_error" in tx or tx.get("meta") is None: continue
        m, t = tx["meta"], tx["transaction"]
        keys = t["message"]["accountKeys"] + m.get("loadedAddresses", {}).get("writable", []) + m.get("loadedAddresses", {}).get("readonly", [])
        ixs = [(ix, "top") for ix in t["message"]["instructions"]] + [(ix, "inner") for g in m.get("innerInstructions") or [] for ix in g["instructions"]]
        transfers, nonce = [], False
        for ix, where in ixs:
            if keys[ix["programIdIndex"]] != SYS: continue
            d = T.b58d(ix["data"])
            if d[:4] == b"\x04\0\0\0": nonce = True
            if d[:4] == b"\x02\0\0\0" and len(d) >= 12 and len(ix["accounts"]) >= 2:
                dest = keys[ix["accounts"][1]]
                if dest != who: transfers.append((dest, int.from_bytes(d[4:12], "little"), where))
        f = T.facts(tx, -1, tx["slot"])
        paths = sorted({SERVICE[d] for d, _, _ in transfers if d in SERVICE})
        for d, l, w in transfers:
            if d not in SERVICE and l < 50_000_000: unknown[(d, w)] += 1
        rows.append({"ok": f["ok"], "win": f["ok"] and f["signer_sol_wsol_change"] > 0, "slot": tx["slot"], "paths": paths, "nonce": nonce,
                     "tips": {SERVICE[d]: l for d, l, _ in transfers if d in SERVICE}, "cu_price": f["cu_price"] or 0, "version": f["version"],
                     "inner_tip": any(w == "inner" and d in SERVICE for d, _, w in transfers)})
    if not rows: continue
    # where its landed transactions ran: leader distance vs the base rate
    lo, hi = min(r["slot"] for r in rows), max(r["slot"] for r in rows)
    lead = {}
    if hi - lo < 5000:
        lr = T.rpc("getSlotLeaders", [lo, hi - lo + 1])
        if isinstance(lr, list): lead = {lo + i: k for i, k in enumerate(lr)}
    need = [k for k in {lead.get(r["slot"]) for r in rows} | set(list(lead.values())[::40]) if k and k not in _rtt]
    with cf.ThreadPoolExecutor(16) as ex: _rtt.update(dict(zip(need, ex.map(lambda k: ping(ip.get(k)), need))))
    def near(slot):
        r = _rtt.get(lead.get(slot)); return None if r is None else r / 2 < 5
    wins, fails = [r for r in rows if r["win"]], [r for r in rows if not r["ok"]]
    base = [near(s) for s in list(lead)[::10] if near(s) is not None]
    wn = [near(r["slot"]) for r in wins if near(r["slot"]) is not None]
    fn = [near(r["slot"]) for r in fails if near(r["slot"]) is not None]
    pc = lambda xs: dict(collections.Counter(tuple(x["paths"]) or ("no tip",) for x in xs).most_common(5))
    print(f"\n{who}  sampled {len(rows)}: wins {len(wins)}, other ok {len(rows)-len(wins)-len(fails)}, failed {len(fails)}")
    print(f"  intended sender (tip instruction) on WINS {pc(wins)} | on FAILURES {pc(fails)}")
    tip_amt = collections.defaultdict(list)
    for r in rows:
        for k, v in r["tips"].items(): tip_amt[k].append(v)
    print(f"  tip amounts median {{ {', '.join(f'{k}: {q(v,.5)}' for k,v in tip_amt.items())} }} | tip paid inside its program (inner) {sum(r['inner_tip'] for r in rows)}")
    print(f"  durable nonce: wins {sum(r['nonce'] for r in wins)}/{len(wins)}, failures {sum(r['nonce'] for r in fails)}/{len(fails)} | cu_price median wins {q([r['cu_price'] for r in wins],.5)} fails {q([r['cu_price'] for r in fails],.5)} | versions {dict(collections.Counter(r['version'] for r in rows))}")
    if base and wn: print(f"  lands on leaders <5 ms from Cherry: wins {sum(wn)*100//len(wn)}% (n={len(wn)}), failures {sum(fn)*100//max(1,len(fn))}% vs all leaders {sum(base)*100//len(base)}% (n={len(base)})")
    prog = collections.Counter()
    summary.append({"who": who, "n": len(rows), "wins": len(wins), "fail_pct": len(fails) * 100 // len(rows),
        "no_tip_wins_pct": sum(1 for r in wins if not r["paths"]) * 100 // max(1, len(wins)),
        "no_tip_all_pct": sum(1 for r in rows if not r["paths"]) * 100 // len(rows),
        "paths": dict(collections.Counter(p for r in rows for p in r["paths"])),
        "nonce_fail_pct": sum(r["nonce"] for r in fails) * 100 // max(1, len(fails)), "nonce_win_pct": sum(r["nonce"] for r in wins) * 100 // max(1, len(wins)),
        "cu_win": q([r["cu_price"] for r in wins], .5), "cu_fail": q([r["cu_price"] for r in fails], .5),
        "v1_pct": sum(1 for r in rows if r["version"] == "1") * 100 // len(rows),
        "near_win_pct": sum(wn) * 100 // len(wn) if wn else None, "near_base_pct": sum(base) * 100 // len(base) if base else None})
print("\nUNKNOWN transfer destinations (possible other senders' tip accounts), most frequent:")
for (d, w), n in unknown.most_common(15): print(f"  {d} ({w}) x{n}")
json.dump(summary, open("/root/arb-lab/runs/rivals-paths.json", "w"), indent=1)
print("\nTABLE who | n | wins | fail% | no-tip wins% | no-tip all% | nonce on fails% | nonce on wins% | cu win/fail | v1% | wins near/base % | paths")
for x in summary:
    print(f"  {x['who'][:8]} | {x['n']} | {x['wins']} | {x['fail_pct']} | {x['no_tip_wins_pct']} | {x['no_tip_all_pct']} | {x['nonce_fail_pct']} | {x['nonce_win_pct']} | {x['cu_win']}/{x['cu_fail']} | {x['v1_pct']} | {x['near_win_pct']}/{x['near_base_pct']} | {x['paths']}")

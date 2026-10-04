#!/usr/bin/env python3
"""exp4 per-gap rival table. Episodes as caps2.py. For every rival arbitrage that took profit from an episode's pools:
signer, ms after the trigger on the leader's PoH clock, profit, trade size (largest WSOL flow through a pool vault,
from getTransaction), priority fee / tip / sender (rivals.jsonl). Then: who works the big gaps, with what size and
speed; our expected profit at each budget for the same gaps. usage: caps3.py <run dir>  (on Cherry: RPC)"""
import json, sys, os, collections, urllib.request, time, concurrent.futures as cf
os.chdir("/root/arb-lab")
RUN = sys.argv[1].rstrip("/"); USD = 119.25; WSOL = "So11111111111111111111111111111111111111112"
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#")); U = env["RMR_RPC_URL"]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
s8 = lambda s: b58d(s)[:8].hex()
q = lambda v, p: (sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None)
caps = [json.loads(l) for l in open(f"{RUN}/caps.jsonl")]
opps = {json.loads(l)["id"]: json.loads(l) for l in open(f"{RUN}/opportunities.jsonl")}
st = [json.loads(l) for l in open(f"{RUN}/status.jsonl")]; hours = (st[-1]["t_ns"] - st[0]["t_ns"]) / 3.6e12
tiers = [c[0] for c in caps[0]["caps"]]
A = {x["opp"]: x for x in map(json.loads, open(f"{RUN}/attempts.jsonl"))}
O = {x["attempt"]: x for x in map(json.loads, open(f"{RUN}/outcomes.jsonl"))}
ep = []; last = {}
for c in caps:
    k = (c["buy"], c["sell"]); e = last.get(k)
    if e and c["slot"] - e["slot_last"] <= 5:
        e["slot_last"] = c["slot"]; e["ids"].append(c["id"])
        for i, x in enumerate(c["caps"]):
            if x[2] is not None and (e["caps"][i] is None or x[2] > e["caps"][i]): e["caps"][i] = x[2]; e["sizes"][i] = x[1]
    else:
        e = {"buy": c["buy"], "sell": c["sell"], "pair": f'{c["buy_venue"]}>{c["sell_venue"]}', "mint": c["mint"], "slot": c["slot"], "slot_last": c["slot"],
             "ids": [c["id"]], "caps": [x[2] for x in c["caps"]], "sizes": [x[1] for x in c["caps"]], "kind": c["kind"]}
        ep.append(e); last[k] = e
moves = collections.defaultdict(list)
for l in open(f"{RUN}/moves.log"):
    p = l.split()
    if len(p) >= 4: moves[p[2]].append((int(p[1]), p[0]))
want = {s for v in moves.values() for _, s in v}
gain = {}
for l in open(f"{RUN}/exec.jsonl"):
    if '"ok":true' not in l: continue
    x = json.loads(l)
    if x["sig"] in want and not {k for k, v in x["tok"].items() if k != WSOL}:
        g = x["sol"] + int(x["tok"].get(WSOL, "0"))
        if g > 0: gain[x["sig"]] = (g, x["signer"], x["fee"])
for e in ep:
    took = {}
    for pool in (e["buy"], e["sell"]):
        for slot, s in moves.get(pool, []):
            if e["slot"] <= slot <= e["slot_last"] + 5 and s in gain: took[s] = gain[s]
    e["took"] = took
    trig = opps.get(e["ids"][0], {}).get("trigger"); e["trig"] = trig
rsig = {s for e in ep for s in e["took"]}
need8 = {s8(s): s for s in rsig} | {s8(e["trig"]): e["trig"] for e in ep if e["trig"]}
poh = {}
for l in open(f"{RUN}/poh.log"):
    p = l.split()
    if len(p) == 3 and p[0] in need8 and p[0] not in poh: poh[p[0]] = int(p[1]) * 400 + float(p[2])
riv = {}
for l in open(f"{RUN}/rivals.jsonl"):
    if any(s in l for s in ()): pass
    x = json.loads(l)
    if x["sig"] in rsig: riv[x["sig"]] = x
def size(sig):
    for i in range(3):
        try:
            r = urllib.request.Request(U, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}]}).encode(), {"content-type": "application/json"})
            t = json.load(urllib.request.urlopen(r, timeout=30)).get("result")
            if not t: return None
            m = t["meta"]; signer = t["transaction"]["message"]["accountKeys"][0]
            pre = {b["accountIndex"]: b for b in m["preTokenBalances"]}; post = {b["accountIndex"]: b for b in m["postTokenBalances"]}
            best = 0
            for k in set(pre) | set(post):
                b = pre.get(k) or post.get(k)
                if b["mint"] != WSOL or b.get("owner") == signer: continue
                d = abs(int((post.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"]) - int((pre.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"]))
                best = max(best, d)
            return best
        except Exception: time.sleep(1 + i)
with cf.ThreadPoolExecutor(8) as ex: sizes = dict(zip(rsig, ex.map(size, rsig)))
rows = []
for e in ep:
    tp = poh.get(s8(e["trig"])) if e["trig"] else None
    att = next((A[i] for i in e["ids"] if i in A), None); out = O.get(att["attempt"]) if att else None
    for s, (g, signer, fee) in e["took"].items():
        if s == e["trig"]: continue   # a state trigger on the rival's own arbitrage: not a reaction to anything
        rp = poh.get(s8(s)); rv = riv.get(s, {})
        rows.append({"mint": e["mint"], "pair": e["pair"], "signer": signer, "profit": g / 1e9, "size": (sizes.get(s) or 0) / 1e9,
            "ms": round(rp - tp, 1) if (rp is not None and tp is not None) else None, "fee": fee, "cu_price": rv.get("cu_price"),
            "tips": rv.get("tips"), "nonce": bool(rv.get("nonce")), "prog": (rv.get("progs") or [None])[0],
            "our_exp": [x / 1e9 if x else 0 for x in e["caps"]], "we": (out or {}).get("landed") and ("WON" if out.get("ok") else "lost") or ("sent" if att else "-")})
json.dump({"hours": hours, "tiers": tiers, "rows": rows, "episodes": len(ep)}, open(f"{RUN}/caps-rivals.json", "w"))
print(f"{len(caps)} priced -> {len(ep)} gap episodes in {hours:.2f} h; {len(rows)} rival profits on them, {sum(r['profit'] for r in rows):.3f} SOL ({sum(r['profit'] for r in rows) / hours:.2f} SOL/h)")
print("\nrival profits by trade size:")
for lo, hi in ((0, .2), (.2, 2), (2, 8.4), (8.4, 21), (21, 1e9)):
    sel = [r for r in rows if lo <= r["size"] < hi]
    print(f"  size {lo:>5}-{hi if hi < 1e9 else 'inf':>4} SOL: {len(sel):4} wins, {sum(r['profit'] for r in sel):8.3f} SOL ({sum(r['profit'] for r in sel) / hours:7.2f}/h), median profit {q([r['profit'] for r in sel], .5) or 0:.5f}, ms after trigger p50 {q([r['ms'] for r in sel if r['ms'] is not None], .5)}, bots {len({r['signer'] for r in sel})}")
print("\nwho works the big gaps (size >= 2 SOL):")
by = collections.defaultdict(list)
for r in rows: by[r["signer"]].append(r)
for sg, rs in sorted(by.items(), key=lambda x: -sum(r["profit"] for r in x[1]))[:15]:
    big = [r for r in rs if r["size"] >= 2]
    tipn = collections.Counter(t[2] or "?" for r in rs for t in (r["tips"] or []) if t[2])
    print(f"  {sg[:8]} wins {len(rs):4} profit {sum(r['profit'] for r in rs):7.3f} SOL | size p50 {q([r['size'] for r in rs], .5):.2f} max {max(r['size'] for r in rs):.1f} SOL | big-size wins {len(big)} ({sum(r['profit'] for r in big):.3f} SOL) | ms p50 {q([r['ms'] for r in rs if r['ms'] is not None], .5)} | cu_price p50 {q([r['cu_price'] or 0 for r in rs], .5)} | nonce {sum(r['nonce'] for r in rs)} | tips {dict(tipn)}")

#!/usr/bin/env python3
# How would a shred-only engine see the dip triggers? Joins trig_sigs.jsonl (events, P&L, followers) with trig_tx.jsonl (RPC truth):
#  1. share of triggers whose pump sell is a TOP-LEVEL instruction (decodable from shreds), and the P&L they carry, per pick set
#  2. the outer programs ("routers") carrying the routed ones
#  3. how fast the first backrunner buys after a top-level vs a routed trigger (block-position proxy, ms) -> do pros see routed
#     sells as early as direct ones?
# usage: python3 -I trig_analyze.py trig_sigs.jsonl trig_tx.jsonl
import sys, json, collections, statistics
EV = [json.loads(l) for l in open(sys.argv[1])]
TX = {}
for l in open(sys.argv[2]):
    r = json.loads(l); TX[r["sig"]] = r
GUARD = 1.02
def pnl_g(e, L):
    if e["src"] == "all":
        p = (e.get("pnl") or {}).get(L); px = (e.get("px") or {}).get(L, 1.0)
    else:
        p = e["pnl"]; px = e.get("px") or 1.0
    if p is None: return None, None
    return p, (p if px <= GUARD else -0.0002)
print("events", len(EV), "with sig", sum(1 for e in EV if e.get("sig")), "fetched", sum(1 for e in EV if e.get("sig") in TX))
for src in sorted({e["src"] for e in EV}):
    E = [e for e in EV if e["src"] == src and e.get("sig") in TX and TX[e["sig"]].get("kind") != "nofetch"]
    if not E: continue
    L = src.split("_L")[1] if src.startswith("oof_L") else "75"
    agg = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for e in E:
        k = TX[e["sig"]]["kind"]; p, pg = pnl_g(e, L)
        if p is None: continue
        a = agg[k]; a[0] += 1; a[1] += p; a[2] += pg
    n = sum(a[0] for a in agg.values())
    print(f"\n{src} (P&L at {L} ms, 2-slot exit): {n} triggers")
    for k in ("top", "routed", "other"):
        a = agg.get(k, [0, 0, 0])
        print(f"   {k:6s} n {a[0]:5d} ({a[0] / max(n, 1):5.1%})  P&L {a[1]:+7.2f}  with 2% guard {a[2]:+7.2f}")
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
       "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"}
def router_of(t):
    r = t.get("router") or {}
    if r.get("prog") and r["prog"] not in STD: return r["prog"], (r["disc"], r["dlen"], r["nacc"], r["mintpos"])
    p = next((p for p in t.get("outer", []) if p not in STD and p != "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"), None)
    return (p or "?"), None
R = collections.Counter(); RS = collections.defaultdict(set); RL = collections.defaultdict(collections.Counter); RP = collections.defaultdict(lambda: collections.defaultdict(float))
for e in EV:
    t = TX.get(e.get("sig"))
    if t and t["kind"] == "routed":
        p, lay = router_of(t); R[p] += 1; RS[p].add(e["user"])
        if lay: RL[p][lay] += 1
        if e["src"].startswith("oof_L"): RP[p][e["src"]] += pnl_g(e, e["src"].split("_L")[1])[1] or 0
print("\nrouters carrying the routed triggers (all sets, with duplicates): program, triggers, distinct sellers, guarded P&L of picks at 35/75 ms, top layouts (disc, data len, accounts, mint position)")
for p, c in R.most_common(15):
    print(f"   {p[:12]}  {c:5d}  sellers {len(RS[p]):4d}  pnl35 {RP[p]['oof_L35']:+5.2f} pnl75 {RP[p]['oof_L75']:+5.2f}  {RL[p].most_common(3)}")
top_disc = collections.Counter(TX[e["sig"]]["top"]["disc"] for e in EV if e.get("sig") in TX and TX[e["sig"]]["kind"] == "top")
print("\ntop-level sell discriminators:", top_disc.most_common(6))
print("\nfirst buy after the trigger, same slot (block-position proxy, ms after the trigger; 'all' events):")
for k in ("top", "routed"):
    d = []; dh = []; who = collections.Counter()
    for e in EV:
        if e["src"] != "all" or e.get("sig") not in TX or TX[e["sig"]]["kind"] != k: continue
        f = next((x for x in e.get("fol", []) if x[1] == 1), None)
        if f and f[4] == 0: d.append(f[3]); who[f[0]] += 1
        h = next((x for x in e.get("fol", []) if x[0] == "HkQ7hMjy" and x[1] == 1 and x[4] == 0), None)
        if h: dh.append(h[3])
    if d:
        q = statistics.quantiles(d, n=10)
        print(f"   {k:6s} n {len(d):5d}  p10 {q[0]:5.1f}  median {statistics.median(d):5.1f}  p90 {q[-1]:5.1f} | HkQ7hMjy n {len(dh)} median {statistics.median(dh) if dh else float('nan'):5.1f} | first buyers {who.most_common(5)}")

#!/usr/bin/env python3
# Follower test: do wallets buy AFTER him on his no-bundle picks far more often than on rule-matched peers (not mayhem,
# dev>=0.5)? Then re-measure the 10 s outcome with his AND those followers' net SOL removed from the curve.
import json, collections, statistics as st

D = "/root/nob/"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
FEE = 0.0125
ds = {json.loads(l)["mint"]: json.loads(l) for l in open(D + "ds.jsonl")}
his = json.load(open(D + "his_mints.json"))
blk = {}
for f in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for l in open(D + f):
        r = json.loads(l)
        if not r.get("missing"):
            blk.setdefault(r["mint"], r)
fo = {}
for l in open(D + "follow.jsonl"):
    x = json.loads(l)
    if "err" not in x:
        fo[x["mint"]] = x


def trades(m):
    """chronological trades S..S+25: (slot, buy, user, sol, vsol)"""
    r = blk[m]
    out = []
    for x in r["later"]:
        if x.get("ok"):
            for e in x["ev"]:
                out.append((r["slot"], e[0], e[1], e[2], e[4]))
    for t in fo[m]["tr"]:
        out.append(tuple(t))
    return out


H = [m for m in fo if fo[m]["grp"] == "his"]
P = [m for m in fo if fo[m]["grp"] == "peer"]
print(f"his no-bundle picks with full 10 s trades: {len(H)}; rule-matched random peers (not mayhem, dev>=0.5): {len(P)}")
print(f"sampled (>150 txs in 10 s): his {sum(1 for m in H if fo[m].get('sampled'))}, peers {sum(1 for m in P if fo[m].get('sampled'))}")

after_h = collections.Counter()   # wallet bought this pick in a slot AFTER his first buy slot
any_h = collections.Counter()
any_p = collections.Counter()
for m in H:
    hb = his[m]["buys"][0]["slot"]
    cr = blk[m]["creator"]
    seen_after, seen = set(), set()
    for s, b, u, sol, v in trades(m):
        if not b or u == W or u == cr:
            continue
        seen.add(u)
        if s > hb:
            seen_after.add(u)
    for u in seen_after:
        after_h[u] += 1
    for u in seen:
        any_h[u] += 1
for m in P:
    cr = blk[m]["creator"]
    for u in {u for s, b, u, sol, v in trades(m) if b and u != cr}:
        any_p[u] += 1
nH, nP = len(H), len(P)
F = set()
rows = []
for u, n in after_h.items():
    rh = n / nH
    rp = (any_p[u] + 0.5) / nP
    if n >= 5 and rh / rp >= 4:
        F.add(u)
    rows.append((n, u, any_p[u], rh / rp))
rows.sort(reverse=True)
print(f"\nwallets buying AFTER him on >=5 of his picks: {sum(1 for r in rows if r[0]>=5)}; of those, 'followers' (>=4x more often than on peers): {len(F)}")
print("top co-buyers after him: wallet, his picks (after him), peers, rate ratio")
for n, u, npeer, ratio in rows[:15]:
    print(f"   {u[:12]}  his {n:3d}/{nH}  peers {npeer:3d}/{nP}  ratio {ratio:5.1f}  {'FOLLOWER' if u in F else ''}")


def outcome(m, remove):
    r = blk[m]
    base = r["base"]
    net = 0
    seq = []
    for s, b, u, sol, v in trades(m):
        if u in remove:
            net += sol if b else -sol
        seq.append((s - r["slot"], ((v - net) / base) ** 2))
    peak = max([p for d, p in seq if d <= 25] + [1.0])
    entry = 1.02
    ex = None
    last = 1.0
    for d, p in seq:
        if d > 25:
            break
        last = p
        if p >= entry * 1.3:
            ex = entry * 1.3
            break
    ex = ex if ex is not None else last
    return peak, ex / entry * (1 - FEE) ** 2 - 1


def fol_sol(m):
    return sum(sol for s, b, u, sol, v in trades(m) if b and u in F) / 1e9


def summ(ms, remove_fn, lab):
    pk, rt = [], []
    for m in ms:
        p, x = outcome(m, remove_fn(m))
        pk.append(p)
        rt.append(x)
    print(f"  {lab:<58} n={len(ms):3d} peak10 med {st.median(pk):.3f} p75 {sorted(pk)[3*len(pk)//4]:.3f}  X10 mean {st.mean(rt):+.3f} win {100*sum(1 for x in rt if x>0)/len(rt):.0f}%  TP-hit {100*sum(1 for x in rt if x>0.2)/len(rt):.0f}%")


print(f"\nfollower buy SOL in the first 10 s: his picks mean {st.mean(fol_sol(m) for m in H):.2f} SOL (share of picks with any: {100*sum(1 for m in H if fol_sol(m)>0)/nH:.0f}%), peers mean {st.mean(fol_sol(m) for m in P):.2f}")
print("\nOutcome over the first 10 s (entry 1.02x at create, TP +30% else exit at 10 s):")
summ(H, lambda m: set(), "his picks, raw")
summ(H, lambda m: {W}, "his picks, his own SOL removed")
summ(H, lambda m: {W} | F, "his picks, his + follower SOL removed")
summ(P, lambda m: set(), "peers, raw")
summ(P, lambda m: F, "peers, follower SOL removed")

print("\nSensitivity: wider follower definitions (wallets buying after him on >=k of his picks, rate ratio vs peers >= r)")
for k, rr in ((5, 3), (5, 2), (3, 2), (3, 0)):
    F2 = {u for n, u, npeer, ratio in rows if n >= k and ratio >= rr}
    pk, rt = [], []
    for m in H:
        p, x = outcome(m, {W} | F2)
        pk.append(p); rt.append(x)
    pk2, rt2 = [], []
    for m in P:
        p, x = outcome(m, F2)
        pk2.append(p); rt2.append(x)
    print(f"  k>={k} ratio>={rr}: {len(F2):3d} wallets removed | his picks peak10 med {st.median(pk):.3f} X10 {st.mean(rt):+.3f} TP-hit {100*sum(1 for x in rt if x>0.2)/len(rt):.0f}%"
          f" | peers peak10 med {st.median(pk2):.3f} X10 {st.mean(rt2):+.3f} TP-hit {100*sum(1 for x in rt2 if x>0.2)/len(rt2):.0f}%")
# demand that arrives in the create slot BEFORE his buy is visible (offset-0: ahead of him; offset-1: whole slot S)
ahead = []
for m in H:
    r = blk[m]
    n = 0
    for x in r["later"]:
        if x.get("his"):
            break
        if x.get("ok") and not x.get("glued") and any(e[0] for e in x["ev"]):
            n += 1
    ahead.append(n)
print(f"\nindependent buys landing before his buy in the create slot: mean {st.mean(ahead):.2f}, share of picks with >=1: {100*sum(1 for a in ahead if a)/len(ahead):.0f}%")

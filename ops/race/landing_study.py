#!/usr/bin/env python3
# READ-ONLY LANDING STUDY. Who lands <= 25 txs behind a pump create, and how? Every OK outside buy in the create slot S:
#   historical: /root/nob/blk_*.jsonl (Oct 14-18, random sample + 4yFAz picks), leader client from the record
#   tonight:    /root/race/{fwd,night}_onchain.jsonl (forward paper runs, a census of base launches), client via getSlotLeaders
#   per buyer:  /root/indep/buyers.jsonl (sender, fee, client) + /root/race/jito_fast.json (bundles.jito.wtf)
#   ours:       /root/race/live_fires.jsonl (today's 42 live buys, payer FRZh63L6)
# Outsider = race_lib rule (not creator / create signers / glued creator bundle; a pro wallet in the glued run counts).
# Time after the create = position d x 217 ms / non-vote txs in the block.
import sys, json, collections, statistics as st, os
sys.path.insert(0, "/root/race")
from race_lib import W, OURS
sys.path.insert(0, "/root/nob")

SLOT_MS = 217.0
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
pros = set(json.load(open("/root/race/pros.json")))
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}


def q(v, p):
    v = sorted(v)
    return v[int(p * (len(v) - 1))] if v else None


def leaders_for(slots):
    from nrpc import rpc
    cache_f = "/root/race/leaders_cache.json"
    cache = json.load(open(cache_f)) if os.path.exists(cache_f) else {}
    need = sorted(s for s in set(slots) if str(s) not in cache)
    i = 0
    while i < len(need):
        lo = need[i]
        r = rpc("getSlotLeaders", [lo, 5000])
        if isinstance(r, list):
            for k, l in enumerate(r):
                cache[str(lo + k)] = l
        while i < len(need) and need[i] < lo + 5000:
            i += 1
    json.dump(cache, open(cache_f, "w"))
    return {int(k): v for k, v in cache.items()}


def client_of(leader):
    return (nodes.get(leader) or {}).get("clientId", "?")


def outsider_txs(b, client, src):
    """yield one dict per tx (OK or failed) touching the mint in S after the create, with outsider/creator side flags."""
    creator, user = b["creator"], b["user"]
    later = b.get("later") or []
    cset = {creator, user, b.get("payer")} | set(b.get("signers") or []) | OURS
    broken = False
    side = {}
    for x in later:
        if x.get("glued"):
            if broken or x["payer"] in pros or x.get("his"):
                broken = True
            else:
                cset.add(x["payer"])
                for e in x["ev"]:
                    cset.add(e[1])
    nnv, cnv = b.get("nnv") or 1000, b.get("cnv") or 0
    mpt = SLOT_MS / max(nnv, 1)
    per_payer = collections.Counter(x["payer"] for x in later)
    for x in later:
        evb = [e for e in x["ev"] if e[0]]
        own = x["payer"] == ME
        outside = x["payer"] not in cset and not (evb and {e[1] for e in evb} <= cset)
        yield {"src": src, "mint": b["mint"], "d": x["d"], "ms": x["d"] * mpt, "payer": x["payer"], "ok": x.get("ok"), "buy": bool(evb),
               "sol": sum(e[2] for e in evb) / 1e9, "cu": x.get("cu_price") or 0, "tips": x.get("tips") or [], "client": client,
               "his": bool(x.get("his")) or x["payer"] == W, "ours": own, "outside": outside or own, "n_payer_txs": per_payer[x["payer"]],
               "create_ms_in_slot": cnv * mpt, "rem_ms": (nnv - cnv) * mpt}


def sender(t):
    if not t["tips"]:
        return "none"
    best = max(t["tips"], key=lambda z: z[1])
    return best[0]


def tipsol(t):
    return max((z[1] for z in t["tips"]), default=0) / 1e9


rows = []
# historical blocks
for fn in ("blk_rand.jsonl", "blk_rand2.jsonl", "blk_his.jsonl"):
    for l in open("/root/nob/" + fn):
        try:
            b = json.loads(l)
        except Exception:
            continue
        if "later" not in b:
            continue
        rows += list(outsider_txs(b, b.get("client", "?"), "hist"))
# tonight
tonight = []
for fn, tag in (("/root/race/fwd_onchain.jsonl", "fwd1"), ("/root/race/night_onchain.jsonl", "night")):
    if not os.path.exists(fn):
        continue
    for l in open(fn):
        try:
            r = json.loads(l)
        except Exception:
            continue
        b = r.get("b") or {}
        if "later" in b:
            tonight.append((b, tag))
L = leaders_for([b["slot"] for b, _ in tonight])
for b, tag in tonight:
    rows += list(outsider_txs(b, client_of(L.get(b["slot"])), tag))
# ours (live)
for l in open("/root/race/live_fires.jsonl"):
    r = json.loads(l)
    b = r.get("b") or {}
    if "later" in b:
        Ll = leaders_for([b["slot"]])
        rows += [t for t in outsider_txs(b, client_of(Ll.get(b["slot"])), "live") if t["ours"]]

buys = [t for t in rows if t["ok"] and t["buy"] and t["outside"] and not t["ours"]]
print(f"outside OK buys in slot S: {len(buys)} (historical {sum(t['src'] == 'hist' for t in buys)}, tonight {sum(t['src'] != 'hist' for t in buys)}); "
      f"our live buys in S: {sum(1 for t in rows if t['ours'] and t['ok'])}")


def bucket(d):
    return "d<=5" if d <= 5 else "d6-25" if d <= 25 else "d26-100" if d <= 100 else "d>100"


def describe(g, label):
    if not g:
        print(f"   {label}: n=0")
        return
    sc = collections.Counter(sender(t) for t in g)
    cc = collections.Counter(t["client"] for t in g)
    cu = [t["cu"] for t in g]
    ts = [tipsol(t) for t in g if t["tips"]]
    print(f"   {label:28} n={len(g):5} | ms after create p50 {q([t['ms'] for t in g], .5):6.1f} | cu_price p50 {q(cu, .5) / 1e6:7.2f}M p75 {q(cu, .75) / 1e6:7.2f}M p90 {q(cu, .9) / 1e6:7.1f}M | "
          f"tipped {len(ts) / len(g):4.0%} tip p50 {q(ts, .5) if ts else 0:.4f} | txs by same payer in S p50 {q([t['n_payer_txs'] for t in g], .5)} (>1: {sum(t['n_payer_txs'] > 1 for t in g) / len(g):.0%})")
    print(f"   {'':28} senders: " + ", ".join(f"{k} {v / len(g):.0%}" for k, v in sc.most_common(7)))
    print(f"   {'':28} leader client: " + ", ".join(f"{k} {v / len(g):.0%}" for k, v in cc.most_common(5)))


print("\n== 1. Outside buys in S by landing position (all data)")
for bk in ("d<=5", "d6-25", "d26-100", "d>100"):
    describe([t for t in buys if bucket(t["d"]) == bk], bk)
print("\n   tonight only:")
for bk in ("d<=5", "d6-25", "d26-100", "d>100"):
    describe([t for t in buys if bucket(t["d"]) == bk and t["src"] != "hist"], bk)
mine = [t for t in rows if t["ours"] and t["ok"]]
print("\n== 2. OUR live buys that landed in S (today; Helius/staked/Nozomi arms, cu_price 100M x 90k CU = 0.009 SOL)")
describe(mine, "ours")
print("   our positions d: " + str(sorted(t["d"] for t in mine)))

print("\n== 3. Who wins the front (d<=25) by LEADER CLIENT: share of fast buys per sender, and the median position of each sender")
for cl in ("AgaveBam", "Harmonic", "JitoLabs", "Firedancer", "Agave"):
    g = [t for t in buys if t["client"] == cl]
    if len(g) < 30:
        continue
    fast = [t for t in g if t["d"] <= 25]
    sc = collections.Counter(sender(t) for t in fast)
    allc = collections.Counter(sender(t) for t in g)
    cells = []
    for s_, n in sc.most_common(6):
        dd = [t["d"] for t in g if sender(t) == s_]
        cells.append(f"{s_} {n / len(fast):.0%} of fast (fast-rate {n / allc[s_]:.0%}, med d {q(dd, .5)})")
    print(f"   {cl:11} outside buys {len(g):5}, fast {len(fast):4} ({len(fast) / len(g):.0%}) | " + "; ".join(cells))

print("\n== 4. Priority: share of outside buys landing d<=25, by cu_price tier (same data)")
for lo, hi, nm in ((0, 1e5, "<0.1M"), (1e5, 1e6, "0.1-1M"), (1e6, 1e7, "1-10M"), (1e7, 1e8, "10-100M"), (1e8, 1e18, ">=100M (ours)")):
    g = [t for t in buys if lo <= t["cu"] < hi]
    if g:
        print(f"   cu_price {nm:14} n={len(g):5} | d<=25 {sum(t['d'] <= 25 for t in g) / len(g):4.0%} | d<=5 {sum(t['d'] <= 5 for t in g) / len(g):4.0%} | med d {q([t['d'] for t in g], .5)}")

print("\n== 5. The fastest wallets: >= 3 buys at d<=25 (wallet, n fast / n all, med d, typical sender, cu_price, txs per launch, client mix)")
byw = collections.defaultdict(list)
for t in buys:
    byw[t["payer"]].append(t)
top = sorted(((sum(t["d"] <= 25 for t in g), w, g) for w, g in byw.items()), key=lambda z: -z[0])
for nfast, w, g in top[:15]:
    if nfast < 3:
        break
    sc = collections.Counter(sender(t) for t in g).most_common(2)
    cc = collections.Counter(t["client"] for t in g if t["d"] <= 25).most_common(3)
    print(f"   {w[:10]}{' (4yFAz)' if w == W else ''} fast {nfast:3}/{len(g):4} | med d {q([t['d'] for t in g], .5):4} | {sc} | cu p50 {q([t['cu'] for t in g], .5) / 1e6:.1f}M | "
          f"txs/launch p50 {q([t['n_payer_txs'] for t in g], .5)} | fast on {cc}")
his = [t for t in rows if t["his"] and t["buy"]]
print("\n== 6. 4yFAz in slot S: positions of his OK buys and his sprays (all his txs in S, incl. failed)")
hok = [t for t in his if t["ok"]]
print(f"   OK buys {len(hok)} | d p25/p50/p75 {q([t['d'] for t in hok], .25)}/{q([t['d'] for t in hok], .5)}/{q([t['d'] for t in hok], .75)} | ms after create p50 {q([t['ms'] for t in hok], .5):.1f}")
allhis = [t for t in rows if t["his"]]
per_launch = collections.Counter(t["mint"] for t in allhis)
print(f"   his txs per launch in S (OK + failed): p50 {q(list(per_launch.values()), .5)}, p90 {q(list(per_launch.values()), .9)}; failed share {sum(not t['ok'] for t in allhis) / max(1, len(allhis)):.0%}")
describe(hok, "4yFAz OK buys")

print("\n== 7. Jito bundles (bundles.jito.wtf) for independent buyers in S (indep sample, Oct 16-17)")
try:
    J = json.load(open("/root/race/jito_fast.json"))
    IB = [json.loads(l) for l in open("/root/indep/buyers.jsonl")]
    for nm, f in (("independent d<=5", lambda b: b.get("cls") == "INDEP" and b["off"] <= 5), ("independent d6-25", lambda b: b.get("cls") == "INDEP" and 6 <= b["off"] <= 25),
                  ("independent d26-150 (sample)", lambda b: b.get("cls") == "INDEP" and 26 <= b["off"] <= 150), ("4yFAz", lambda b: b.get("user") == W or b.get("payer") == W)):
        g = [b for b in IB if b.get("sd") == 0 and f(b) and b["sig"] in J and not J[b["sig"]].get("err")]
        inb = [b for b in g if J[b["sig"]].get("in_bundle")]
        with_create = 0
        for b in inb:
            txs = J[b["sig"]].get("txs") or []
            if len(txs) > 1:
                with_create += 1
        cc = collections.Counter(b["client"] for b in inb)
        print(f"   {nm:30} checked {len(g):4} | in a Jito bundle {len(inb):4} ({len(inb) / max(1, len(g)):.0%}) | multi-tx bundles {with_create} | leader client of those: {dict(cc)}")
    # what senders the fast independents used in that sample
    g = [b for b in IB if b.get("sd") == 0 and b.get("cls") == "INDEP" and b["off"] <= 25]
    print("   fast independents' senders (indep classifier): " + ", ".join(f"{k} {v}" for k, v in collections.Counter(b["sender"] for b in g).most_common(8)))
    print("   fast independents' priority SOL (fee - base) p50 %.5f p90 %.5f" % (q([b["prio"] / 1e9 for b in g], .5), q([b["prio"] / 1e9 for b in g], .9)))
except Exception as ex:
    print("   jito data not ready:", ex)

print("\n== 8. Create position inside its slot and the time left for a same-slot entry (tonight)")
cr = {}
for t in rows:
    if t["src"] != "hist":
        cr[t["mint"]] = (t["create_ms_in_slot"], t["rem_ms"])
v = list(cr.values())
print(f"   launches {len(v)} | create at p25/p50/p75 {q([a for a, _ in v], .25):.0f}/{q([a for a, _ in v], .5):.0f}/{q([a for a, _ in v], .75):.0f} ms into the slot | "
      f"time left in S after the create p25/p50/p75 {q([b for _, b in v], .25):.0f}/{q([b for _, b in v], .5):.0f}/{q([b for _, b in v], .75):.0f} ms")

print("\n== 9. Same relay, different speed: buys tipped to Helius Sender (outsiders) vs ours")
hel = [t for t in buys if sender(t) == "helius_sender"]
print(f"   outside Helius-tipped buys in S: n={len(hel)} | d p10/p25/p50/p75 {q([t['d'] for t in hel], .1)}/{q([t['d'] for t in hel], .25)}/{q([t['d'] for t in hel], .5)}/{q([t['d'] for t in hel], .75)} | "
      f"ms after create p10/p25/p50 {q([t['ms'] for t in hel], .1):.1f}/{q([t['ms'] for t in hel], .25):.1f}/{q([t['ms'] for t in hel], .5):.1f} | share d<=25 {sum(t['d'] <= 25 for t in hel) / max(1, len(hel)):.0%}")
fh = [t for t in hel if t["d"] <= 25]
print(f"   the fast ones (d<=25, n={len(fh)}): cu_price p50 {q([t['cu'] for t in fh], .5) / 1e6 if fh else 0:.1f}M | tip p50 {q([tipsol(t) for t in fh], .5) if fh else 0:.4f} | client " + str(collections.Counter(t['client'] for t in fh).most_common(4)))
ourh = [t for t in mine if sender(t) == "helius_sender"]
print(f"   ours via Helius in S: n={len(ourh)} | d {sorted(t['d'] for t in ourh)} | ms after create p50 {q([t['ms'] for t in ourh], .5) if ourh else 0:.1f}")
ahead = collections.Counter()
nlaunch = 0
for t in mine:
    g = [u for u in buys if u["mint"] == t["mint"] and u["d"] < t["d"]]
    nlaunch += 1
    for u in g:
        ahead[sender(u)] += 1
print(f"   on our {nlaunch} same-slot live buys, outside buys that landed AHEAD of us by sender: " + ", ".join(f"{k} {v}" for k, v in ahead.most_common(8)))

# ---- dump empirical in-S landing positions per sender and leader client (for forward_proof.py landing models)
dist = collections.defaultdict(lambda: collections.defaultdict(list))
for t in buys:
    dist[sender(t)][t["client"]].append(t["d"])
    dist[sender(t)]["ALL"].append(t["d"])
dist["ours"]["ALL"] = sorted(t["d"] for t in mine)
json.dump({k: dict(v) for k, v in dist.items() if k in ("jito", "landx", "helius_sender", "ours", "none", "astralane", "nozomi")}, open("/root/race/landing_dist.json", "w"))
print("\nlanding_dist.json written:", {k: {c: len(v) for c, v in d.items()} for k, d in dist.items() if k in ("jito", "landx", "ours")})

#!/usr/bin/env python3
# INSIDER / LINK CHECKS (read-only RPC + local raw txs):
#  (a) direct: does any of the wallet's own txs (outside its pump trades) touch a creator of a token it traded? (full history for
#      Fsb6/pXGQ; 4vw54: only its trade + token-account txs are known)
#  (b) funding: for a sample of tokens per wallet, who first funded the creator (oldest incoming SOL)? Is it the wallet, one of the
#      wallet's own counterparties, or a funder shared across many of its tokens?
#  (c) the wallet's own main counterparties: balance and recent activity (exchange-like hot wallet or a personal wallet?)
import os, sys, json, gzip, time, random, collections, urllib.request, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
SYS = "11111111111111111111111111111111"
L = lib3.load_launches(); P = [p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if not p.get("nobuy")]
S = json.load(open(os.path.join(lib3.HERE, "out/chain_summary.json")))
def keys_of(t):
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    return msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
def funder(addr, max_pages=3):
    """oldest incoming SOL transfer to addr (System transfer, top-level or inner): (sender, SOL, time) or None"""
    sigs = []; before = None
    for _ in range(max_pages):
        pg = rpc("getSignaturesForAddress", [addr, {"limit": 1000, **({"before": before} if before else {})}]) or []
        sigs += pg
        if len(pg) < 1000: break
        before = pg[-1]["signature"]
    if not sigs: return None, 0
    oldest = [s for s in reversed(sigs) if not s.get("err")][:6]
    for s in oldest:
        t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not t: continue
        keys = keys_of(t)
        if addr not in keys: continue
        i = keys.index(addr)
        if t["meta"]["postBalances"][i] > t["meta"]["preBalances"][i]:
            # the account that lost the most SOL is the sender
            d = [(t["meta"]["postBalances"][k] - t["meta"]["preBalances"][k], keys[k]) for k in range(len(t["meta"]["postBalances"])) if keys[k] != addr]
            snd = min(d)[1] if d else None
            return (snd, (t["meta"]["postBalances"][i] - t["meta"]["preBalances"][i]) / 1e9, lib3.pkt(t.get("blockTime") or 0), len(sigs) >= 1000 * max_pages), len(sigs)
    return None, len(sigs)
out = {}
random.seed(7)
for w8, W in lib3.W3.items():
    o = {}
    pos = [p for p in P if p["w"] == w8]
    creators = {L[p["m"]]["creator"]: p["m"] for p in pos if p["m"] in L}
    # (a) direct links in the wallet's own txs
    direct = []
    def lines(fn):
        try:
            for l in gzip.open(fn, "rt"): yield l
        except (EOFError, OSError): return
    for fn in (f"raw/{w8}.jsonl.gz", f"raw/{w8}_ata_a.jsonl.gz", f"raw/{w8}_ata_b.jsonl.gz"):
        if not os.path.exists(fn): continue
        for l in lines(fn):
            try: t = json.loads(l)
            except Exception: continue
            ks = set(keys_of(t))
            hit = ks & set(creators)
            if hit and W in ks:
                # ignore the pump trade itself where the creator is only the fee-vault owner: check SOL moves between wallet and creator
                keys = keys_of(t); pre, post = t["meta"]["preBalances"], t["meta"]["postBalances"]
                for c in hit:
                    i = keys.index(c)
                    dc = post[i] - pre[i] if i < len(post) else 0
                    if dc != 0: direct.append(dict(sig=t["sig"], creator=c, creator_dsol=dc / 1e9, payer=keys[0][:8], t=lib3.pkt(t.get("blockTime") or 0)))
    o["creators"] = len(creators); o["direct_sol_links"] = direct[:20]; o["n_direct_sol_links"] = len(direct)
    # (b) sample creators' funders
    samp = random.sample(sorted(creators), min(12, len(creators)))
    with cf.ThreadPoolExecutor(6) as ex: res = list(ex.map(funder, samp))
    cps = {k for k, *_ in (S[w8].get("plain_transfers") or [])} | {k for k, _ in (S[w8].get("flow_counterparties") or [])}
    fl = []
    for c, (f, n) in zip(samp, res):
        fl.append(dict(creator=c, mint=creators[c], funder=f[0] if f else None, sol=f[1] if f else None, t=f[2] if f else None, n_sigs=n,
                       funder_is_wallet=bool(f and f[0] == W), funder_is_wallet_counterparty=bool(f and f[0] in cps)))
    o["creator_funders"] = fl
    o["shared_funders"] = collections.Counter(x["funder"] for x in fl if x["funder"]).most_common(5)
    # top repeat followers (copy bots?): who funded them — the wallet itself or its counterparties would mean self-trading
    FO = json.load(open(os.path.join(lib3.HERE, "out/followers.json")))[w8]["top"][:4]
    with cf.ThreadPoolExecutor(4) as ex: fr_ = list(ex.map(funder, [x["wallet"] for x in FO]))
    o["follower_funders"] = [dict(follower=x["wallet"], rate=x["rate"], funder=f[0] if f else None, sol=f[1] if f else None, t=f[2] if f else None, n_sigs=n,
                                  funder_is_wallet=bool(f and f[0] == W), funder_is_wallet_counterparty=bool(f and f[0] in cps)) for x, (f, n) in zip(FO, fr_)]
    for x in o["follower_funders"]: print(f"   follower {x['follower'][:8]} ({x['rate']:.0%} of first buys) funded by {str(x['funder'])[:8]} at {x['t']} | sigs {x['n_sigs']} | is the wallet {x['funder_is_wallet']} | wallet counterparty {x['funder_is_wallet_counterparty']}")
    out[w8] = o
    print(f"\n## {w8}: creators of its tokens {len(creators)} | txs moving SOL between it and a creator: {len(direct)}")
    for d in direct[:8]: print("   ", d)
    for x in fl: print(f"   creator {x['creator'][:8]} funded by {str(x['funder'])[:8]} ({x['sol']}) at {x['t']} | sigs {x['n_sigs']} | is the wallet: {x['funder_is_wallet']} | is one of the wallet's counterparties: {x['funder_is_wallet_counterparty']}")
    print("   most common creator funders:", o["shared_funders"])
# (c) the wallets' own counterparties
cpo = {}
for name, addr in [("Fsb6 withdrawals -> Aza3Lv3T", "Aza3Lv3TLHs8WkHzYNVd88zetSe14gtdRbXAeX6QKudp"), ("Fsb6 deposits <- 69SNcRC8", "69SNcRC8NqjHBSXEcugCN5oFKRQoKmddmWzZYc3tqtxk"),
                   ("pXGQ relayer FHpcNSe6", "FHpcNSe6tb2n15bAdq4BkeYWGyZKFD7yLYrH92ng7wCT"), ("4vw54 tip receiver J4PeVZhx", "J4PeVZhx2496eXjAMpbm7nrCxRBgAUfRDwhZ1YSdzTSE")]:
    b = rpc("getBalance", [addr]); pg = rpc("getSignaturesForAddress", [addr, {"limit": 1000}]) or []
    span = (pg[0]["blockTime"] - pg[-1]["blockTime"]) if len(pg) > 1 and pg[0].get("blockTime") and pg[-1].get("blockTime") else None
    cpo[name] = dict(addr=addr, balance=(b or {}).get("value", 0) / 1e9 if b else None, last1000_span_s=span, n=len(pg))
    print(f"\n{name}: balance {cpo[name]['balance']} SOL | last {len(pg)} txs span {span} s")
out["counterparties"] = cpo
json.dump(out, open(os.path.join(lib3.HERE, "out/links.json"), "w"), indent=1)

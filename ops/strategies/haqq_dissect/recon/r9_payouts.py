#!/usr/bin/env python3
"""recon step 9 (read-only): break down every payout (Jupiter-route) tx in the window: SOL sent by haqq per destination,
SOL routed into the SOL->USDC swap, USDC received per owner (token-balance deltas). Out: recon/r9.txt"""
import json, glob, collections, time
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
WSOL_ACC = "3aoEhd6mTk7q6beUTVYHFoF79tFrQdoXcqXP5wiHxSQy"
G = {}
for fx in sorted(glob.glob(f"{OUT}/gettx*.jsonl")):
    for l in open(fx):
        j = json.loads(l)
        if j.get("res") is not None and j["why"] == "unrec": G[j["sig"]] = j["res"]
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
tot_sol = collections.Counter(); tot_usdc = collections.Counter(); tot_out = 0; n = 0
for sig, res in sorted(G.items(), key=lambda kv: kv[1]["slot"]):
    msg = res["transaction"]["message"]; meta = res["meta"]
    if not any((x.get("programId") or "").startswith("JUP6") for x in msg["instructions"]): continue
    keys = [k["pubkey"] for k in msg["accountKeys"]]
    la = meta.get("loadedAddresses") or {}; keys += (la.get("writable") or []) + (la.get("readonly") or [])
    hi = keys.index(H); d = meta["postBalances"][hi] - meta["preBalances"][hi]
    sent = collections.Counter()
    for x in msg["instructions"]:
        p = x.get("parsed")
        if isinstance(p, dict) and p.get("type") == "transfer" and x.get("program") == "system" and p["info"]["source"] == H:
            sent[p["info"]["destination"]] += int(p["info"]["lamports"])
    pre = {(t["accountIndex"]): t for t in meta["preTokenBalances"]}; post = {(t["accountIndex"]): t for t in meta["postTokenBalances"]}
    usd = collections.Counter()
    for k in set(pre) | set(post):
        a = pre.get(k) or post.get(k)
        if a["mint"] != USDC: continue
        v0 = int((pre.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"]); v1 = int((post.get(k) or {"uiTokenAmount": {"amount": "0"}})["uiTokenAmount"]["amount"])
        usd[a.get("owner")] += v1 - v0
    n += 1; tot_out += d
    P(f"\n### payout {n}: {pkt(res['blockTime'])} PKT, wallet {d / 1e9:+.6f} SOL, fee {meta['fee']}  https://solscan.io/tx/{sig}")
    tsent = sum(sent.values())
    for dst, v in sent.most_common():
        P(f"  SOL -> {dst}  {v / 1e9:.6f} SOL ({v / tsent:.1%})" + ("   [his WSOL account: swapped to USDC]" if dst == WSOL_ACC else ""))
        tot_sol[dst] += v
    for o, v in sorted(usd.items(), key=lambda kv: -kv[1]):
        if v > 0: P(f"  USDC +{v / 1e6:.6f} to owner {o}"); tot_usdc[o] += v
P(f"\n## Totals over {n} payouts: wallet {tot_out / 1e9:+.6f} SOL")
for dst, v in tot_sol.most_common(): P(f"  SOL -> {dst}  {v / 1e9:.6f}" + ("   (swapped to USDC)" if dst == WSOL_ACC else ""))
for o, v in tot_usdc.most_common(): P(f"  USDC -> owner {o}  {v / 1e6:.4f} USDC")
open(f"{OUT}/r9.txt", "w").write("\n".join(L) + "\n")

#!/usr/bin/env python3
# INSTANT-BOTS study, step 12 (read-only RPC, cached, paced): H4 link check. For (seller, instant buyer) pairs: the first SOL funding
# of each wallet (oldest signature -> that tx -> the account that sent it SOL) and, for the buyer, whether its SOL came from the
# seller or a shared funder. Only for wallets with a short history (fresh rotation wallets): at most MAXPAGES pages of 1000 sigs.
# usage: python3 -I i12_funding.py PAIRS.json OUT.json      (PAIRS = [[label, seller, buyer], ...])
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import rpc_ro as R
MAXPAGES = 3
def oldest(w):
    before = None; last = None; n = 0
    for _ in range(MAXPAGES):
        p = [w, {"limit": 1000}] if before is None else [w, {"limit": 1000, "before": before}]
        page = R.rpc("getSignaturesForAddress", p) or []
        n += len(page)
        if not page: break
        last = page[-1]; before = last["signature"]
        if len(page) < 1000: return last, n, True
    return last, n, False
def funder(w):
    o, n, complete = oldest(w)
    if not o: return dict(w=w, n_sigs=0)
    t = R.tx(o["signature"])
    if not t: return dict(w=w, n_sigs=n, complete=complete, first_sig=o["signature"])
    msg = t["transaction"]["message"]; meta = t["meta"]; la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    d = {keys[j]: meta["postBalances"][j] - meta["preBalances"][j] for j in range(min(len(keys), len(meta["preBalances"])))}
    src = sorted(((k, v) for k, v in d.items() if v < 0 and k != w), key=lambda x: x[1])
    return dict(w=w, n_sigs=n, complete=complete, first_sig=o["signature"], first_slot=o.get("slot"), first_time=o.get("blockTime"),
                received=d.get(w), payer=msg["accountKeys"][0], top_sender=src[0][0] if src else None, top_sent=src[0][1] if src else None)
pairs = json.load(open(sys.argv[1])); out = []
for lab, s, b in pairs:
    fs, fb = funder(s), funder(b)
    link = None
    if fb.get("top_sender") == s or fb.get("payer") == s: link = "buyer funded by the seller"
    elif fs.get("top_sender") and fs.get("top_sender") == fb.get("top_sender"): link = "shared funder"
    elif fs.get("payer") and fs.get("payer") == fb.get("payer") and fs.get("payer") not in (s, b): link = "same fee payer of the first tx"
    out.append(dict(label=lab, seller=fs, buyer=fb, link=link))
    print(f"{lab:14s} seller {s[:8]} first funded by {str(fs.get('top_sender'))[:8]} (payer {str(fs.get('payer'))[:8]}, sigs {fs.get('n_sigs')}{'' if fs.get('complete') else '+'}) | "
          f"buyer {b[:8]} first funded by {str(fb.get('top_sender'))[:8]} (payer {str(fb.get('payer'))[:8]}, sigs {fb.get('n_sigs')}{'' if fb.get('complete') else '+'}) -> {link}", flush=True)
json.dump(out, open(sys.argv[2], "w"), indent=1)
print("rpc calls", R.calls())

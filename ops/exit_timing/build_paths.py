#!/usr/bin/env python3
"""Reconstruct full bonding-curve price-vs-slot path for our 8 live trades.
price = |SOL delta| / |token delta| on the bonding curve, per trade, paginated.
Reuses common.py (rpc, gettx, _keys). px units: SOL per whole-token (common convention).
Our given entry prices are lamports/raw-token = px_common * 1000, so we convert for r."""
import sys, os, json, time
sys.path.insert(0, "/root/profit_backtest")
import common as C

TRADES = [
 ("883Xw2k39itvFRMPBJYXx91MAw3uzc2sKqiRSAQaFb55","8YaN82Z3JEGeh3kqA5PAcnwGdzyK3ABu5dwpbmeUdA87",4.614232e-5,456975817),
 ("3nfCAA4emVMQpbqVCzEHx9XHursYSdtUw9rfcQzepump","E9V2LtnAuwvd2KS9q8xAmDwpwKwK5C1nCYC77cDdVuZN",4.337700e-5,456976243),
 ("CenpWbd7YgwRi13DLEgudX1wwDhBFapv8fL4dzeopump","5eMbCLAD8kD4tB73d82kTJy7yYKM5Tqgq9FfAwmAqSWf",3.630786e-5,456976481),
 ("2mczEAedUhHRP5GQ43gP2qTVWCij9NgfidmNJpya4YKU","8D2mStWdzAVSALn6QJiYKRRLbfPsT9diJak7MgabRNK1",5.581127e-5,456976619),
 ("7Cs9KCipGn4s5GSjBEKdeqQ4CJ8aXwvSunY9Lre1fDKE","FXui5fYmpXkiGY38bKWafWG7qFNmBmPr6meXzATKbp5f",4.500714e-5,456977279),
 ("FXUVymBHRSNaYyuVdkdNhRU8boEP5doyU4ceV6bswrh2","H9BQcaYucNV5qXjSUZfJuA6WzaWe8bZBXvjwVZuVE6zf",5.158643e-5,456977469),
 ("BEms6yQdym89E2d71pypdpjdQ8ZyeuKXtBSdaYqWpump","5E5dZwvD3zK2YUDbAp5V26Re7Am6qd2yB7jAeRpnhYXU",4.092492e-5,456977646),
 ("8FYmQHVr33Li3YykhXKpshLvHGjZksHV9MDHdZ9epump","AqGqDUDGuP7KSr3FzMuRVKrBhnhmCerky87KMKhjQEQ", 4.284795e-5,456977932),
]
UNIT = 1000.0  # px_common(SOL/whole-tok) * 1000 = lamports/raw-token (6-dec mint)

def paginate_sigs(bc, max_pages=25):
    sigs=[]; before=None; pages=0
    while pages < max_pages:
        pr=[bc,{"limit":1000}]
        if before: pr[1]["before"]=before
        ch=C.rpc("getSignaturesForAddress", pr)
        if not ch: break
        sigs+=ch; before=ch[-1]["signature"]; pages+=1
        if len(ch)<1000: break   # reached oldest (create)
    return sigs

def price_of(tx, bc):
    meta=tx.get("meta")
    if not meta or meta.get("err"): return None
    keys=C._keys(tx)
    def tok(owner):
        pre=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("preTokenBalances",[]) if t.get("owner")==owner)
        post=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("postTokenBalances",[]) if t.get("owner")==owner)
        return post-pre
    dtok=tok(bc); dsol=0.0
    if bc in keys:
        idx=keys.index(bc); dsol=(meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
    if dtok>0 and dsol>0: return None  # create tx (mint + dev buy)
    if abs(dtok)>0 and abs(dsol)>1e-9:
        return (abs(dsol)/abs(dtok), dsol)  # px(SOL/whole-tok), dsol(signed; <0 buy pulls SOL in? no: buy adds SOL)
    return None

out={}
for mint,bc,entry,exitslot in TRADES:
    bc2=C.bonding_curve_of(mint)
    assert bc2==bc, f"bc mismatch {mint}: derived {bc2} != given {bc}"
    sigs=paginate_sigs(bc)
    good=[s for s in sigs if not s["err"]]
    good.sort(key=lambda s:(s["slot"], s["signature"]))
    series=[]  # (slot, blockTime, px_common, dsol)
    from concurrent.futures import ThreadPoolExecutor
    def fetch(s):
        tx=C.gettx(s["signature"])
        if not tx: return None
        p=price_of(tx, bc)
        if p is None: return None
        return (s["slot"], tx.get("blockTime"), p[0], p[1])
    with ThreadPoolExecutor(max_workers=24) as ex:
        for r in ex.map(fetch, good):
            if r: series.append(r)
    series.sort(key=lambda x:(x[0],))
    out[mint]={"bc":bc,"entry_lamports_raw":entry,"exit_slot":exitslot,
               "n_sigs":len(sigs),"n_trades":len(series),
               "create_slot": series[0][0] if series else None,
               "series":[[s,bt,round(px,18),round(ds,9)] for (s,bt,px,ds) in series]}
    print(f"{mint[:10]} sigs={len(sigs)} trades={len(series)} create~{out[mint]['create_slot']} exit={exitslot} span={series[-1][0]-series[0][0] if series else 0}", flush=True)

json.dump(out, open("/root/exit_timing/paths.json","w"))
print("WROTE /root/exit_timing/paths.json")

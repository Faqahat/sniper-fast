import json, os, sys
from block_curve import analyze

SOFF=30_000_000_000              # virtual SOL offset (lamports)
TOFF=73_000_000_000_000          # virtual token offset (base units)
RTOK_INIT=1_000_000_000_000_000  # initial real token in curve
K=SOFF*(RTOK_INIT+TOFF)          # constant product on virtual reserves

def price_at(real_token):
    vtok=real_token+TOFF
    vsol=K/vtok
    return vsol/vtok   # lamports per base token (marginal)

PROBES=[
 {"n":1,"mint":"A8FjoUQXDywuGTrBaeLvDPHtyVq3LaM6YCH4Prfhpump","curve":"2yqGMNPcdYby3K3agMHJYe912URLkiu84cfgTMrUq2Eb","buy_sig":"5ru3kg8FuDGBGrpkKo3zrX6DjPNNBfGz8eGMHy54GAgp7vASGcrUHBtzeVSGqnd17EB8DQU6tth5SgBgk5mAttrz","dev":3.0,"create":456917832,"buy_slot":456917833},
 {"n":2,"mint":"U5jNL2jHg88FKCdf9gdDZHLHvGyPkUvtgQzjEojpump","curve":"7ahdY1LDSihE7pvu862obyee9hjGpyesJ17i3APodjY9","buy_sig":"5jFMEZqzFsWCPjak2obCcYWarXV3EV692gfuDBLXwpuEBAS84MRWjwFJJbPmqHo1kejMGMvyRRsRkbcP7H2TcWn4","dev":2.0,"create":456918320,"buy_slot":456918321},
 {"n":3,"mint":"4WXrvNPHY1K38MLYwYtuqU8mTsyaTTgWKgu8BmuPpump","curve":"Az1VJe5w1yPbZ6PvT5RKJj2V39VPYF4PrYEJXLyMYYFj","buy_sig":"5mHKoPcSABn4nLXHfy3CmsHaTnHQ1VCHzZE4R1JkbHH5iN1pDENeXkbjWrH6kamefRCtw11ADYgCXBaL94edjGAq","dev":2.0,"create":456918406,"buy_slot":456918406},
 {"n":4,"mint":"F7YM1TjmsLU6pR1QGCqzrahJDbmtWiv22Pg8aezJpump","curve":"3JVFGai9W75PrNzzk5E7CM2rzzMTTJhbKSC6B8r9LqhW","buy_sig":"46ycZb5VUXVgH2Q4oaSfWaT21zhUgrhcoYTwyA71RqCB4c6EL3fEVCNNQ2c9rB8jprB7k6yRFsC5YJEh6Eior67D","dev":2.5,"create":456918640,"buy_slot":456918641},
 {"n":5,"mint":"3xHxWfcaBLvgny1tVVz7tkcu1x7LtKKAEE1ksWbgVM9U","curve":"E3GuRy2aYwpowhBujJfAS7wBN23yB1etGQnFbjeeNi6B","buy_sig":"5X5RsrfJeKYtwnPbbMnv1aH9ba6L9T13xEPdske162A63VomHL66sXgwcHx3EZM9zyMcAGmaisUbiPJiGv89DaXW","dev":5.0,"create":456919487,"buy_slot":456919488},
]
OUR="FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"

def run(p):
    slots=sorted(set([p["create"],p["create"]+1,p["create"]+2,p["buy_slot"]]))
    trades=[]   # ordered successful curve-balance-changing buys across slots
    allcurvetx=[]
    for s in slots:
        res=analyze(s,p["curve"],p["mint"],OUR)
        if not res: 
            sys.stderr.write(f"no block {s}\n"); continue
        for t in res["txs"]:
            t["slot"]=s
            allcurvetx.append(t)
    # global order: by slot, then block_index
    allcurvetx.sort(key=lambda t:(t["slot"],t["block_index"]))
    # successful buys = curve_tok_delta<0 (tokens leaving curve) OR create (rtok_pre None with buyer_tok_delta>0)
    seq=[]
    for t in allcurvetx:
        if t["err"] is not None: continue
        # create/dev-buy: rtok_pre None but buyer got tokens
        is_create = (t["curve_tok_delta"] is None and t["buyer_tok_delta"]>0)
        is_buy = (t["curve_tok_delta"] is not None and t["curve_tok_delta"]<0)
        if is_create or is_buy:
            seq.append(t)
    # reconstruct real_token trajectory. For create, real_token after = RTOK_INIT - buyer_tok_delta
    results=[]
    floor_price=None
    our_entry=None
    rank_in_seq=None
    buys_before_us=0
    for i,t in enumerate(seq):
        if t["curve_tok_delta"] is None:
            rtok_post = RTOK_INIT - t["buyer_tok_delta"]
            rtok_pre = RTOK_INIT
        else:
            rtok_post = t["rtok_post"]
            rtok_pre = t["rtok_pre"]
        marg_pre=price_at(rtok_pre)
        marg_post=price_at(rtok_post)
        avg=(t["curve_lam_delta"]/t["buyer_tok_delta"]) if t["buyer_tok_delta"] else None
        rec={"i":i,"slot":t["slot"],"idx":t["block_index"],"ours":t["is_ours"],"payer":t["payer"],
             "tokens":t["buyer_tok_delta"],"sol_in":t["curve_lam_delta"],
             "marg_pre":marg_pre,"marg_post":marg_post,"avg":avg,
             "is_create":t["curve_tok_delta"] is None}
        results.append(rec)
        if rec["is_create"] and floor_price is None:
            floor_price=marg_post   # price immediately after dev buy
        if t["is_ours"]:
            our_entry=rec
            rank_in_seq=i+1
            buys_before_us=i  # number of successful buys before ours
    # co-sniper distinct buyers per slot
    from collections import defaultdict
    buyers_by_slot=defaultdict(set)
    attempts_by_slot=defaultdict(int)
    for t in allcurvetx:
        buyers_by_slot[t["slot"]].add(t["payer"])
        attempts_by_slot[t["slot"]]+=1
    return {"probe":p,"floor":floor_price,"our":our_entry,"rank":rank_in_seq,
            "buys_before_us":buys_before_us,"seq":results,
            "buyers_by_slot":{s:len(buyers_by_slot[s]) for s in sorted(buyers_by_slot)},
            "attempts_by_slot":{s:attempts_by_slot[s] for s in sorted(attempts_by_slot)}}

if __name__=="__main__":
    out=[]
    for p in PROBES:
        r=run(p)
        out.append(r)
        print(f"\n===== PROBE {p['n']}  mint {p['mint'][:8]} dev {p['dev']} SOL  create {p['create']} buy {p['buy_slot']} (land=create+{p['buy_slot']-p['create']}) =====")
        print(f"  successful buy sequence (create-slot + next slots):")
        for rec in r["seq"]:
            mark=" <<< OURS" if rec["ours"] else ""
            tag="CREATE/DEVBUY" if rec["is_create"] else "buy"
            print(f"   seq{rec['i']:>2} slot{rec['slot']} idx{rec['idx']:>5} {tag:14s} payer {rec['payer'][:6]} tokens {rec['tokens']:>18d} sol_in {rec['sol_in']:>12d} marg_post {rec['marg_post']:.6e}{mark}")
        fl=r["floor"]; our=r["our"]
        if our and fl:
            our_fill=our["avg"]
            exec_marg=our["marg_pre"]
            print(f"  FLOOR (marg after devbuy) = {fl:.6e} lam/tok")
            print(f"  OUR_FILL (avg)            = {our_fill:.6e} lam/tok")
            print(f"  price WHEN WE EXECUTED (marg pre-our) = {exec_marg:.6e}")
            print(f"  FILL_RATIO (our_fill/floor) = {our_fill/fl:.4f}")
            print(f"  exec_marg/floor = {exec_marg/fl:.4f}")
            print(f"  intra-seq rank = {r['rank']}  (successful buys before us = {r['buys_before_us']})")
        else:
            print(f"  !! could not locate our buy in seq (our={bool(our)} floor={bool(fl)})")
        bs={s:f"{r['buyers_by_slot'][s]}({r['attempts_by_slot'][s]})" for s in r['buyers_by_slot']}
        print("  distinct buyers (attempts) by slot:", bs)
    json.dump(out,open("results.json","w"))

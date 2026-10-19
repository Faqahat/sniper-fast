#!/usr/bin/env python3
"""Atomic-arb detector over cached blocks: round-trip txs (start/end in SOL/wSOL), net positive."""
import os,json,glob,collections
WSOL="So11111111111111111111111111111111111111112"
PROG={
"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":"pumpfun_bc",
"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA":"pumpswap_amm",
"675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8":"raydium_ammv4",
"CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK":"raydium_clmm",
"CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C":"raydium_cpmm",
"JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4":"jupiter_v6",
"LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo":"meteora_dlmm",
"whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc":"orca_whirlpool",
"Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB":"meteora_pools",
"5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j":"raydium_launchlab",
}
SWAP=set(PROG.values())-{"jupiter_v6"}
JITO_TIPS=set("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5 HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49 DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh ADuUkR4vqLUMWXxW9gh6D6L8pGm 3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT".split())

def tokdelta(meta,owner):
    """net token delta per mint for owner (ui amounts)."""
    pre=collections.defaultdict(float); post=collections.defaultdict(float)
    for t in meta.get("preTokenBalances",[]) or []:
        if t.get("owner")==owner: pre[t["mint"]]+=float(t["uiTokenAmount"]["uiAmountString"] or 0)
    for t in meta.get("postTokenBalances",[]) or []:
        if t.get("owner")==owner: post[t["mint"]]+=float(t["uiTokenAmount"]["uiAmountString"] or 0)
    d={}
    for m in set(pre)|set(post):
        dd=post[m]-pre[m]
        if abs(dd)>1e-9: d[m]=dd
    return d

arbs=[]; sellers=collections.Counter(); arb_by_signer=collections.Counter(); arb_profit_by_signer=collections.Counter()
n_tx=0; n_swap=0
for f in glob.glob("/root/landscape/blocks/*.json"):
    try: b=json.load(open(f))
    except: continue
    if not b: continue
    for tx in b.get("transactions",[]):
        meta=tx.get("meta") or {}
        if meta.get("err"): continue
        n_tx+=1
        msg=tx["transaction"]["message"]
        acct=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
        if not acct: continue
        signer=acct[0]
        progs=set()
        for ix in msg.get("instructions",[]):
            if ix.get("programId"): progs.add(ix["programId"])
        for inner in meta.get("innerInstructions",[]) or []:
            for ix in inner.get("instructions",[]):
                if ix.get("programId"): progs.add(ix["programId"])
        named={PROG[p] for p in progs if p in PROG}
        venues=named & SWAP
        if not (venues or "jupiter_v6" in named): continue
        n_swap+=1
        i=acct.index(signer)
        sol_d=(meta["postBalances"][i]-meta["preBalances"][i])  # lamports, net incl fee
        td=tokdelta(meta,signer)
        # wSOL delta folded into SOL
        wsol_d=td.pop(WSOL,0.0)
        eff_sol=sol_d/1e9 + wsol_d  # SOL + wSOL change (approx, wsol 1:1 SOL)
        # non-sol token residual (did they end flat?)
        resid=sum(abs(v) for v in td.values())
        # count venue program instances across inner for multi-pool
        tip=0
        for ix in msg.get("instructions",[]):
            pr=ix.get("parsed")
            if isinstance(pr,dict) and pr.get("type")=="transfer" and pr.get("info",{}).get("destination") in JITO_TIPS:
                tip+=int(pr["info"].get("lamports",0))
        # ATOMIC ARB: ended flat in tokens (resid ~ 0 meaning no net token acquired) and SOL+wSOL up
        is_arb = (resid < 1e-6) and (eff_sol > 0)
        if is_arb:
            arbs.append({"sig":tx["transaction"]["signatures"][0],"signer":signer,"venues":sorted(venues|({ "jupiter_v6"} if "jupiter_v6" in named else set())),"profit_sol":round(eff_sol,6),"tip":tip,"n_venues":len(venues)})
            arb_by_signer[signer]+=1; arb_profit_by_signer[signer]+=eff_sol

arbs.sort(key=lambda x:-x["profit_sol"])
tot=sum(a["profit_sol"] for a in arbs)
pos=[a for a in arbs if a["profit_sol"]>0.0005]
print(f"swap_tx={n_swap} atomic_arb_tx={len(arbs)} (profit>0.5mSOL: {len(pos)})")
print(f"total arb profit (gross, pre-tip): {tot:.3f} SOL over window")
tottip=sum(a["tip"] for a in arbs)/1e9
print(f"total jito tips paid by arbs: {tottip:.3f} SOL ; net after tips: {tot-tottip:.3f} SOL")
print("top 15 arbs:",[ (a["profit_sol"],a["venues"],round(a["tip"]/1e9,4)) for a in pos[:15]])
print("\ntop arb signers (count, gross profit SOL):")
for s,n in arb_by_signer.most_common(15):
    print(f"  {s} n={n} profit={arb_profit_by_signer[s]:.3f}")
json.dump({"n_arb":len(arbs),"n_pos":len(pos),"tot_profit":tot,"tot_tip":tottip,"arbs":arbs[:300],
           "top_signers":[(s,n,arb_profit_by_signer[s]) for s,n in arb_by_signer.most_common(40)]},
          open("/root/landscape/arb.json","w"))

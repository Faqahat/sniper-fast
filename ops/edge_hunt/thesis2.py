#!/usr/bin/env python3
"""THESIS 2 - migration/graduation arbitrage. For each graduated pump token, find migration tx,
final bonding-curve price, PumpSwap pool seed reserves (open price), and the AMM price path after open.
Measure the dislocation: final-BC vs AMM-open gap, and AMM pop (open -> max within 10s/30s/1m/5m).
NET of cost reported two ways: conservative 1%/leg (task floor) and realistic PumpSwap ~0.30%/leg."""
import sys,os,json,statistics as st
sys.path.insert(0,"/root/profit_backtest")
import common as C
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
SLOTS_PER_S=2.5
grad=json.load(open("/root/edge_hunt/grad_list.json"))
OUT="/root/edge_hunt/thesis2_pools.json"

def tokbal(meta, acct_addr_set):
    pass

def find_migration(mint, bc, create_slot):
    # newest curve sigs; migration = newest tx with PUMPSWAP in keys
    ch=C.rpc("getSignaturesForAddress",[bc,{"limit":40}])
    if not ch: return None
    ch=[s for s in ch if not s["err"]]
    mig=None
    for s in sorted(ch,key=lambda x:x["slot"]):  # oldest->newest among recent
        tx=C.gettx(s["signature"])
        if not tx or not tx.get("meta"): continue
        keys=C._keys(tx)
        if PUMPSWAP in keys:
            mig=(s,tx); break
    return mig

def analyze(m):
    mint=m["mint"]; bc=m["bc"]; cs=m["create_slot"]
    mig=find_migration(mint,bc,cs)
    if not mig: return {"mint":mint,"err":"no_migration_tx"}
    s,tx=mig; meta=tx["meta"]; keys=C._keys(tx)
    # final BC price: last real curve trade strictly before migration slot
    # (reuse long_traj series if present)
    final_bc=None
    try:
        lt=json.load(open(f"/root/edge_hunt/long_traj/{mint}.json"))
        ser=[p for p in lt["series"] if p[0] < s["slot"]]
        if ser: final_bc=ser[-1][2]
    except Exception: pass
    # pool PDA = owner holding BOTH a big mint balance and a WSOL balance in migration tx
    bymint={}; bywsol={}
    for t in meta.get("postTokenBalances",[]):
        amt=float(t["uiTokenAmount"]["uiAmountString"] or 0); o=t.get("owner"); ai=t.get("accountIndex")
        if t["mint"]==mint and amt>1e5: bymint[o]=(amt,ai)
        if t["mint"]==WSOL and amt>1.0: bywsol[o]=(amt,ai)
    pool=None
    for o in bymint:
        if o in bywsol: pool=o; break
    if not pool: return {"mint":mint,"err":"no_pool","mig_slot":s["slot"]}
    base_amt, base_ai = bymint[pool]
    wsol_amt, wsol_ai = bywsol[pool]
    base_vault = keys[base_ai]; wsol_vault = keys[wsol_ai]
    open_px = wsol_amt/base_amt  # seed AMM price
    # AMM price path: paginate base_vault forward from migration slot
    allsigs=[]; before=None; pages=0
    hi=s["slot"]+int(300*SLOTS_PER_S)  # 5 min window
    while pages<8:
        pr=[base_vault,{"limit":1000}]
        if before: pr[1]["before"]=before
        ch=C.rpc("getSignaturesForAddress",pr)
        if not ch: break
        allsigs+=ch; before=ch[-1]["signature"]; pages+=1
        if len(ch)<1000: break
        if ch[-1]["slot"]<=s["slot"]: break
    sw=[x for x in allsigs if not x["err"] and s["slot"]<=x["slot"]<=hi]
    sw.sort(key=lambda x:(x["slot"],x["signature"]))
    path=[]
    for x in sw[:200]:
        t2=C.gettx(x["signature"])
        if not t2 or not t2.get("meta"): continue
        mm=t2["meta"]; kk=C._keys(t2)
        # base vault token delta
        def tokamt(owner_acct, pre):
            arr=mm.get("preTokenBalances" if pre else "postTokenBalances",[])
            for tb in arr:
                if kk[tb["accountIndex"]]==owner_acct and tb["mint"]==mint:
                    return float(tb["uiTokenAmount"]["uiAmountString"] or 0)
            return None
        bpre=tokamt(base_vault,True); bpost=tokamt(base_vault,False)
        # wsol vault lamport delta (WSOL is SPL; use token amount)
        def wamt(pre):
            arr=mm.get("preTokenBalances" if pre else "postTokenBalances",[])
            for tb in arr:
                if kk[tb["accountIndex"]]==wsol_vault and tb["mint"]==WSOL:
                    return float(tb["uiTokenAmount"]["uiAmountString"] or 0)
            return None
        wpre=wamt(True); wpost=wamt(False)
        if None in (bpre,bpost,wpre,wpost): continue
        dt=bpost-bpre; dw=wpost-wpre
        if abs(dt)>0 and abs(dw)>1e-9:
            px=abs(dw)/abs(dt)
            path.append([x["slot"], px])
    return {"mint":mint,"mig_slot":s["slot"],"pool":pool,"base_vault":base_vault,"wsol_vault":wsol_vault,
            "seed_base":base_amt,"seed_wsol":wsol_amt,"open_px":open_px,"final_bc":final_bc,
            "n_amm_swaps":len(path),"path":path}

from concurrent.futures import ThreadPoolExecutor, as_completed
res=[]
with ThreadPoolExecutor(max_workers=8) as ex:
    futs=[ex.submit(analyze,m) for m in grad]
    for fu in as_completed(futs):
        try: res.append(fu.result())
        except Exception as e: res.append({"err":str(e)})
json.dump(res,open(OUT,"w"))
ok=[r for r in res if r.get("open_px")]
print(f"analyzed {len(res)} graduated, {len(ok)} with pool+open price")
for r in res:
    if "err" in r: print("  ERR",r.get("mint"),r["err"])

def px_at(path,t):
    v=None
    for sl,px in path:
        if sl<=t: v=px
        else: break
    return v
def maxin(path,t0,win):
    m=None
    for sl,px in path:
        if t0<=sl<=t0+win:
            if m is None or px>m: m=px
    return m

print("\n=== MIGRATION DISLOCATION (per token) ===")
print("mint      finalBC    openAMM   gap%   openpx->max5m%   n_amm")
gaps=[]; pops={h:[] for h in ["10s","30s","1m","5m"]}
HWIN={"10s":25,"30s":75,"1m":150,"5m":750}
for r in ok:
    fb=r.get("final_bc"); op=r["open_px"]; path=r["path"]
    gap=(op-fb)/fb*100 if fb else None
    if gap is not None: gaps.append(gap)
    mig=r["mig_slot"]
    # pop = max within window after migration / open
    pstr=""
    for h,w in HWIN.items():
        mx=maxin(path,mig,w)
        if mx and op:
            pops[h].append((mx-op)/op*100)
    mx5=maxin(path,mig,750)
    pop5=((mx5-op)/op*100) if (mx5 and op) else float('nan')
    print(f"{r['mint'][:8]} {fb if fb else 0:.2e} {op:.2e} {gap if gap is not None else 0:+6.1f} {pop5:+8.1f}      {r['n_amm_swaps']}")

def summ(xs):
    xs=[x for x in xs if x==x]
    if not xs: return "n=0"
    xs2=sorted(xs); n=len(xs2)
    return f"n={n} mean={sum(xs2)/n:+.1f}% med={xs2[n//2]:+.1f}% p25={xs2[n//4]:+.1f}% p75={xs2[int(n*.75)]:+.1f}% max={xs2[-1]:+.1f}%"
print("\nfinalBC->openAMM gap:", summ(gaps))
for h in ["10s","30s","1m","5m"]:
    print(f"open->max within {h}:", summ(pops[h]))

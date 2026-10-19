#!/usr/bin/env python3
"""THESIS 2 v2 - robust. Price the PumpSwap pool by RESERVE RATIO (wsol_reserve/token_reserve) at
every tx that touches the pool vaults, after the migration. Also get the true final bonding-curve
completion price (last real curve trade). Migration found via the bonding-curve big-SOL-withdraw tx."""
import sys,os,json,statistics as st
sys.path.insert(0,"/root/profit_backtest")
import common as C
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
SLOTS_PER_S=2.5
grad=json.load(open("/root/edge_hunt/grad_list.json"))
OUT="/root/edge_hunt/thesis2_pools_v2.json"

def find_migration(bc, cs):
    """migration = the bonding-curve tx with large negative SOL delta AND PumpSwap in keys (pool create)."""
    ch=C.rpc("getSignaturesForAddress",[bc,{"limit":60}])
    if not ch: return None
    ch=[s for s in ch if not s["err"]]
    cands=[]
    for s in sorted(ch,key=lambda x:x["slot"]):
        tx=C.gettx(s["signature"])
        if not tx or not tx.get("meta"): continue
        keys=C._keys(tx); meta=tx["meta"]
        dsol=0
        if bc in keys:
            i=keys.index(bc); dsol=(meta["postBalances"][i]-meta["preBalances"][i])/1e9
        if PUMPSWAP in keys and dsol < -1.0:   # pool create pulls SOL off the curve
            cands.append((s,tx,dsol))
    if cands: return cands[0]   # earliest = the migration
    # fallback: earliest recent tx with pumpswap
    for s in sorted(ch,key=lambda x:x["slot"]):
        tx=C.gettx(s["signature"])
        if tx and tx.get("meta") and PUMPSWAP in C._keys(tx): return (s,tx,None)
    return None

def final_bc_px(bc, cs, mig_slot):
    """last real curve trade price strictly before migration. paginate curve sigs, fetch the last few before mig."""
    ch=C.rpc("getSignaturesForAddress",[bc,{"limit":80}])
    if not ch: return None
    pre=[s for s in ch if not s["err"] and s["slot"]<mig_slot]
    pre.sort(key=lambda x:x["slot"])
    for s in reversed(pre[-6:]):
        tx=C.gettx(s["signature"])
        if not tx or not tx.get("meta"): continue
        meta=tx["meta"]; keys=C._keys(tx)
        if bc not in keys: continue
        i=keys.index(bc); dsol=(meta["postBalances"][i]-meta["preBalances"][i])/1e9
        def tok(owner):
            pre_=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("preTokenBalances",[]) if t.get("owner")==owner)
            post_=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("postTokenBalances",[]) if t.get("owner")==owner)
            return post_-pre_
        dtok=tok(bc)
        if dtok>0 and dsol>0: continue
        if abs(dtok)>0 and abs(dsol)>1e-9:
            return abs(dsol)/abs(dtok)
    return None

def analyze(m):
    mint=m["mint"]; bc=m["bc"]; cs=m["create_slot"]
    mg=find_migration(bc,cs)
    if not mg: return {"mint":mint,"err":"no_migration"}
    s,tx,dsol=mg; meta=tx["meta"]; keys=C._keys(tx)
    # pool vaults: find pool PDA owning both a mint-vault and a wsol-vault
    bymint={}; bywsol={}
    for t in meta.get("postTokenBalances",[]):
        amt=float(t["uiTokenAmount"]["uiAmountString"] or 0); o=t.get("owner"); ai=t.get("accountIndex")
        if t["mint"]==mint and amt>1e4: bymint.setdefault(o,(amt,ai))
        if t["mint"]==WSOL and amt>0.5: bywsol.setdefault(o,(amt,ai))
    pool=next((o for o in bymint if o in bywsol), None)
    if not pool: return {"mint":mint,"err":"no_pool","mig_slot":s["slot"],
                         "mint_owners":list(bymint),"wsol_owners":list(bywsol)}
    base_amt,base_ai=bymint[pool]; wsol_amt,wsol_ai=bywsol[pool]
    base_vault=keys[base_ai]; wsol_vault=keys[wsol_ai]
    open_px=wsol_amt/base_amt
    fb=final_bc_px(bc,cs,s["slot"])
    # AMM reserve-ratio path: paginate base_vault forward, read both vault reserves per tx
    allsigs=[]; before=None; pages=0; hi=s["slot"]+int(300*SLOTS_PER_S)
    while pages<10:
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
    for x in sw[:250]:
        t2=C.gettx(x["signature"])
        if not t2 or not t2.get("meta"): continue
        kk=C._keys(t2); mm=t2["meta"]
        br=wr=None
        for tb in mm.get("postTokenBalances",[]):
            addr=kk[tb["accountIndex"]]
            if addr==base_vault and tb["mint"]==mint: br=float(tb["uiTokenAmount"]["uiAmountString"] or 0)
            if addr==wsol_vault and tb["mint"]==WSOL: wr=float(tb["uiTokenAmount"]["uiAmountString"] or 0)
        if br and wr and br>0:
            path.append([x["slot"], wr/br])
    return {"mint":mint,"mig_slot":s["slot"],"pool":pool,"open_px":open_px,"final_bc":fb,
            "seed_wsol":wsol_amt,"seed_base":base_amt,"curve_withdraw_sol":dsol,
            "n_amm":len(path),"path":path}

from concurrent.futures import ThreadPoolExecutor, as_completed
res=[]
with ThreadPoolExecutor(max_workers=6) as ex:
    futs=[ex.submit(analyze,m) for m in grad]
    for fu in as_completed(futs):
        try: res.append(fu.result())
        except Exception as e: res.append({"err":repr(e)})
json.dump(res,open(OUT,"w"))
ok=[r for r in res if r.get("open_px") and r.get("path")]
print(f"analyzed {len(res)}, with pool+path {len(ok)}")
for r in res:
    if "err" in r: print("  ERR",r.get("mint","?")[:8],r["err"], r.get("mint_owners",""),r.get("wsol_owners",""))

def maxin(path,t0,win):
    xs=[px for sl,px in path if t0<=sl<=t0+win]
    return max(xs) if xs else None
def minin(path,t0,win):
    xs=[px for sl,px in path if t0<=sl<=t0+win]
    return min(xs) if xs else None

# Net helpers: conservative pump-floor 1%/leg+0.5%slip; realistic PumpSwap 0.30%/leg
def net(g, legfee, slip):  return g*(1-legfee-slip/2)/(1+legfee+slip/2)-1
HWIN={"10s":25,"30s":75,"1m":150,"5m":750}
print("\n=== per-token: buy at AMM OPEN, best sell within window (gross %, and NET @2% / @0.6% fee) ===")
print("mint     openpx    gap(BC%)  | max5m_gross%  net@2%  net@0.6% | drawdown_min5m%")
pops5=[]; nets_cons=[]; nets_real=[]; gaps=[]
for r in ok:
    op=r["open_px"]; path=r["path"]; mig=r["mig_slot"]; fb=r.get("final_bc")
    gap=((op-fb)/fb*100) if fb else None
    if gap is not None: gaps.append(gap)
    mx5=maxin(path,mig,750); mn5=minin(path,mig,750)
    g=(mx5/op) if mx5 else 1.0
    pops5.append((g-1)*100)
    nc=net(g,0.01,0.005)*100; nr=net(g,0.003,0.002)*100
    nets_cons.append(nc); nets_real.append(nr)
    dd=((mn5-op)/op*100) if mn5 else 0
    print(f"{r['mint'][:8]} {op:.2e} {gap if gap is not None else 0:+7.1f}  | {(g-1)*100:+11.1f}  {nc:+7.1f} {nr:+7.1f} | {dd:+8.1f}")

def summ(xs):
    xs=sorted(x for x in xs if x==x)
    if not xs: return "n=0"
    n=len(xs); return f"n={n} mean={sum(xs)/n:+.1f} med={xs[n//2]:+.1f} p25={xs[n//4]:+.1f} p75={xs[int(n*.75)]:+.1f} min={xs[0]:+.1f} max={xs[-1]:+.1f}"
print("\nfinalBC->open gap %:", summ(gaps))
print("open->max5m gross %:", summ(pops5))
print("NET @2% fee (buy open, sell best-5m, PERFECT exit) %:", summ(nets_cons))
print("NET @0.6% PumpSwap fee (perfect exit) %:", summ(nets_real))
# realistic: can't sell at the max. Measure fixed-horizon returns (buy open, sell at +30s and +1m spot)
print("\n=== realistic FIXED-exit (no look-ahead): buy open, sell at +30s / +1m spot ===")
def px_at(path,t):
    v=None
    for sl,px in path:
        if sl<=t: v=px
        else: break
    return v
for h,w in [("+30s",75),("+1m",150),("+5m",750)]:
    gs=[]
    for r in ok:
        op=r["open_px"]; p=px_at(r["path"], r["mig_slot"]+w)
        if p: gs.append(net(p/op,0.003,0.002)*100)
    print(f" sell {h} spot, NET@0.6%: {summ(gs)}")

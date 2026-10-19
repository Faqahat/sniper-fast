#!/usr/bin/env python3
"""Shadow harness — historical replay/backtester for the pump sniper (entry + exit + filter).
No live infra, no sends. Reconstructs each launch's price series from on-chain trades, then replays
our strategy to get counterfactual PnL. Ports exit.rs (ladder) and filter.rs (gate) to python so the
same logic that would ship is what we calibrate.

Usage:
  shadow.py sim <mint> [<mint> ...]     # reconstruct + simulate given mints, print per-mint + aggregate
Caches every tx under /tmp/shadow_cache so reruns are cheap/resumable.
"""
import sys, os, json, time, hashlib, urllib.request, struct
RPC="https://api.mainnet-beta.solana.com"
PUMP_B58="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CACHE="/tmp/shadow_cache"; os.makedirs(CACHE,exist_ok=True)
_B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s: n=n*58+_B58.index(c)
    return (b"\x00"*(len(s)-len(s.lstrip("1"))))+(n.to_bytes((n.bit_length()+7)//8,"big") if n else b"")
def b58enc(b):
    n=int.from_bytes(b,"big"); s=""
    while n: n,r=divmod(n,58); s=_B58[r]+s
    return "1"*(len(b)-len(b.lstrip(b"\x00")))+s
# PDA (ed25519 on-curve) for bonding_curve derivation
p=2**255-19; d=(-121665*pow(121666,p-2,p))%p; I=pow(2,(p-1)//4,p)
def oc(b):
    y=int.from_bytes(b,"little"); sg=(y>>255)&1; y&=(1<<255)-1
    if y>=p: return False
    u=(y*y-1)%p; v=(d*y*y+1)%p; v3=v*v*v%p; v7=v3*v3*v%p
    x=u*v3%p*pow(u*v7%p,(p-5)//8,p)%p; vx2=v*x*x%p
    if vx2==u%p: pass
    elif vx2==(-u)%p: x=x*I%p
    else: return False
    if x==0 and sg: return False
    return True
def fpa(seeds,prog):
    for bump in range(255,-1,-1):
        h=hashlib.sha256()
        for s in seeds: h.update(s)
        h.update(bytes([bump])); h.update(prog); h.update(b"ProgramDerivedAddress")
        c=h.digest()
        if not oc(c): return c
PUMP=b58dec(PUMP_B58)
def rpc(m,pr):
    r=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":pr}).encode(),headers={"Content-Type":"application/json"})
    for a in range(6):
        try: return json.load(urllib.request.urlopen(r,timeout=40))["result"]
        except urllib.error.HTTPError as e:
            time.sleep((1.4*(a+1)) if e.code==429 else 0.6)
        except Exception: time.sleep(0.7)
    return None
def gettx(sig):
    f=os.path.join(CACHE,sig+".json")
    if os.path.exists(f):
        try: return json.load(open(f))
        except: pass
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    json.dump(tx,open(f,"w")); time.sleep(0.3); return tx

# ---------- price trajectory from the bonding curve's trades ----------
# IMPORTANT: anchor on the CREATE slot. The sniper's edge is entering at the create-slot floor, so the
# entry price must be the first trade at/after create — not an arbitrary mid-life trade. We paginate to the
# OLDEST sigs and keep only a window [create_slot, create_slot+win].
def trajectory(mint, create_slot, win=55, max_trades=55):
    bc=b58enc(fpa([b"bonding-curve", b58dec(mint)], PUMP))
    all_sigs=[]; before=None; pages=0
    while pages<10:
        pr=[bc,{"limit":1000}]
        if before: pr[1]["before"]=before
        ch=rpc("getSignaturesForAddress",pr); time.sleep(0.22)
        if not ch: break
        all_sigs+=ch; before=ch[-1]["signature"]; pages+=1
        if len(ch)<1000: break            # reached the OLDEST (create) — have full history
        if ch[-1]["slot"] <= create_slot: break  # oldest page already spans the create slot
    sigs=[s for s in all_sigs if not s["err"] and create_slot <= s["slot"] <= create_slot+win]
    sigs.sort(key=lambda s:(s["slot"], s["signature"]))   # chronological from create
    series=[]  # (slot, t, px)  px = SOL per token for that trade
    for s in sigs[:max_trades]:
        tx=gettx(s["signature"])
        if not tx: continue
        meta=tx["meta"]; keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
        # curve token delta (owner == bonding_curve) and curve SOL (lamports) delta
        def tok(owner):
            pre=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("preTokenBalances",[]) if t.get("owner")==owner)
            post=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in meta.get("postTokenBalances",[]) if t.get("owner")==owner)
            return post-pre
        dtok=tok(bc)
        if bc in keys:
            idx=keys.index(bc); dsol=(meta["postBalances"][idx]-meta["preBalances"][idx])/1e9
        else: dsol=0.0
        if abs(dtok)>0 and abs(dsol)>1e-9:
            px=abs(dsol)/abs(dtok)
            series.append((s["slot"], tx.get("blockTime"), px))
    return series

# ---------- exit ladder (port of exit.rs) ----------
class ExitParams:
    derisk_frac=0.40; ride_r=1.60; ladder_r_floor=1.00; ladder_frac=0.30
    ladder_step_slots=4; trail_drop=0.15; stop_r=0.85; age_cap_slots=50; slippage=0.10
def simulate_exit(entry_px, entry_slot, pos_tokens, series, P=ExitParams):
    remaining=pos_tokens; phase="derisk"; peak_r=1.0; last_sell=entry_slot; sol_out=0.0; sells=[]
    for (slot,t,px) in series:
        if remaining<=pos_tokens*1e-6: break
        r=px/entry_px; peak_r=max(peak_r,r); age=slot-entry_slot
        def sell(frac,reason):
            nonlocal remaining,sol_out,last_sell
            toks=min(remaining,remaining*frac); remaining-=toks; last_sell=slot
            sol_out+=toks*px*(1-P.slippage); sells.append((age,round(r,2),reason,round(100*toks/pos_tokens,1)))
        if r<=P.stop_r or age>=P.age_cap_slots:
            sell(1.0,"stop" if r<=P.stop_r else "agecap"); break
        if phase=="derisk": sell(P.derisk_frac,"derisk"); phase="ladder"; continue
        if phase=="ride":
            if r<=peak_r*(1-P.trail_drop): sell(1.0,"ridestop"); break
        else: # ladder
            if r>=P.ride_r: phase="ride"
            elif r<P.ladder_r_floor: sell(1.0,"fade"); break
            elif slot-last_sell>=P.ladder_step_slots: sell(P.ladder_frac,"ladder")
    if remaining>pos_tokens*1e-6 and series:   # ran out of series: mark remainder at last px
        sol_out+=remaining*series[-1][2]*(1-ExitParams.slippage); sells.append(("end",round(series[-1][2]/entry_px,2),"series-end",round(100*remaining/pos_tokens,1)))
    return sol_out, sells

# ---------- filter (port of filter.rs, intrinsic tier) ----------
def features(mint):
    # create_v2 features from the mint's creation tx
    before=None;earliest=None;pg=0
    while pg<6:
        pr=[mint,{"limit":1000}]
        if before: pr[1]["before"]=before
        ch=rpc("getSignaturesForAddress",pr); time.sleep(0.22)
        if not ch: break
        earliest=ch[-1]; before=ch[-1]["signature"]; pg+=1
        if len(ch)<1000: break
    if not earliest: return None
    tx=gettx(earliest["signature"])
    if not tx: return None
    sdelta=(tx["meta"]["postBalances"][0]-tx["meta"]["preBalances"][0])/1e9
    dev_buy=max(0.0,-sdelta-0.025)
    feebps=0;mayhem=0;uri=""
    for i in tx["transaction"]["message"]["instructions"]:
        if i.get("programId")==PUMP_B58:
            dd=b58dec(i["data"])
            if dd[:8].hex()=="d6904cec5f8b31b4":
                q=8
                for _ in range(3):
                    ln=int.from_bytes(dd[q:q+4],"little"); q+=4+ln
                    if _==2: uri_len=ln
                q+=32; mayhem=dd[q]; q+=1+1; feebps=int.from_bytes(dd[q:q+8],"little")
                # uri presence
                uri="x" if uri_len>0 else ""
                break
    return {"dev_buy":dev_buy,"feebps":feebps,"mayhem":mayhem,"has_uri":uri!="","create_slot":earliest["slot"]}
def filter_pass(f, cfg):
    if f["dev_buy"]<cfg["dev_min"] or f["dev_buy"]>cfg["dev_max"]: return False,"dev_band"
    if f["feebps"]>cfg["max_fee_bps"]: return False,"fee"
    if f["mayhem"] and not cfg["allow_mayhem"]: return False,"mayhem"
    return True,"pass"

CFG={"dev_min":0.5,"dev_max":5.0,"max_fee_bps":100,"allow_mayhem":False,"base_size":2.0}

def sim(mints):
    print("%-20s %6s %7s %5s %7s %8s  %s"%("mint","devSOL","entryPx","pass","sizeSOL","pnlSOL","sells"))
    tot=0.0; n=0; wins=0
    for m in mints:
        f=features(m)
        if not f: print("%-20s  (no create)"%m[:20]); continue
        ser=trajectory(m, f["create_slot"])
        if not ser: print("%-20s dev=%.2f  (no trajectory)"%(m[:20],f["dev_buy"])); continue
        entry_slot=ser[0][0]; entry_px=ser[0][2]
        ok,why=filter_pass(f,CFG)
        if not ok:
            print("%-20s %6.2f %7.2e  SKIP(%s)"%(m[:20],f["dev_buy"],entry_px,why)); continue
        size=CFG["base_size"]; pos_tokens=size/entry_px
        sol_out,sells=simulate_exit(entry_px,entry_slot,pos_tokens,ser[1:])
        pnl=sol_out-size; tot+=pnl; n+=1; wins+= pnl>0
        print("%-20s %6.2f %7.2e  YES %7.2f %8.3f  %s"%(m[:20],f["dev_buy"],entry_px,size,pnl,sells[:5]))
    if n: print("\nAGG sniped=%d  totalPnL=%.3f SOL  win=%.0f%%  exp/snipe=%.3f"%(n,tot,100*wins/n,tot/n))

if __name__=="__main__":
    if len(sys.argv)<3 or sys.argv[1]!="sim":
        print(__doc__); sys.exit(1)
    sim(sys.argv[2:])

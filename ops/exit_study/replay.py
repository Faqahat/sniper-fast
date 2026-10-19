import json,statistics as st
rows=json.load(open("rows2.json"))
paths=json.load(open("paths.json"))
SLOT_MS=215.0
FEE=0.012  # pump 1% + ~0.2% slippage/tip per sell leg

def sim(r0rows, derisk,ride,trail,cut,ladder,cap_ms):
    cap_slots=cap_ms/SLOT_MS
    out=[]
    for r in r0rows:
        m=r["mint"]; p=paths.get(m,{}); pts=p.get("pts",[])
        if not pts or not r["px_entry"]: 
            out.append(None); continue
        pe=r["px_entry"]; bslot=r["bslot"]
        seq=[(s,px/pe) for s,px in pts if s>=bslot]
        if not seq: seq=[(bslot,1.0)]
        remaining=1.0; peak=1.0; riding=False; first=True; last_sell_slot=bslot
        legs=[]; done=False
        for (s,rr) in seq:
            if remaining<=1e-9: break
            if rr>peak: peak=rr
            if (not riding) and rr>=ride: riding=True
            dslot=s-bslot
            if first:
                first=False; qty=min(derisk,remaining); why="derisk"
                legs.append((rr,qty)); remaining-=qty; last_sell_slot=s; continue
            if rr<=cut:
                legs.append((rr,remaining)); remaining=0; done=True; break
            if riding and rr<=peak*trail:
                legs.append((rr,remaining)); remaining=0; done=True; break
            if dslot>=cap_slots:
                legs.append((rr,remaining)); remaining=0; done=True; break
            if (not riding) and rr<1.0 and s>last_sell_slot:
                legs.append((rr,remaining)); remaining=0; done=True; break
            if (not riding) and 1.0<=rr<ride and (s-last_sell_slot)>=4:
                qty=min(remaining*ladder,remaining); legs.append((rr,qty)); remaining-=qty; last_sell_slot=s
        if remaining>1e-9:
            legs.append((seq[-1][1],remaining)); remaining=0
        # PnL normalized: proceeds = sum frac*r*(1-fee); cost=1.0 (entry) ; buy fee approximated in his sol_in already
        proceeds=sum(f*rr*(1-FEE) for rr,f in legs)
        pnl_norm=proceeds-1.0
        out.append(pnl_norm*r["sol_in"])  # scale by actual SOL entry
    return out

his=[r["realized"] for r in rows]
his_sum=sum(his); his_win=sum(1 for x in his if x>0)/len(his)
print(f"HIS actual: sum={his_sum:.3f} mean={his_sum/len(his):.4f} win={his_win:.3f}  n={len(his)}")
print()
cfgs=[
 ("default",0.40,1.6,0.85,0.85,0.30,8000),
 ("derived",0.30,1.40,0.92,0.95,0.25,9000),
 ("derived-tightcut",0.30,1.35,0.92,0.97,0.25,8000),
 ("derived-ride13",0.30,1.30,0.92,0.96,0.25,10000),
 ("derived-cap12",0.30,1.40,0.92,0.95,0.25,12000),
]
for name,*pp in cfgs:
    s=sim(rows,*pp)
    v=[x for x in s if x is not None]
    tot=sum(v); win=sum(1 for x in v if x>0)/len(v)
    # correlation to his per-pos
    pairs=[(h,x) for h,x in zip(his,s) if x is not None]
    print(f"{name:18s} derisk={pp[0]} ride={pp[1]} trail={pp[2]} cut={pp[3]} ladder={pp[4]} cap={pp[5]}")
    print(f"   SIM sum={tot:.3f} mean={tot/len(v):.4f} win={win:.3f}  (his sum {his_sum:.3f})")

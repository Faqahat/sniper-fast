import sys; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve,PUMP,rpc
import json,time
TOKS={
 "PASS1(6uQr,ran,dev~1.3)":"6uQrPwv1DoX7x7QXMbiy1e9FR5mRyhMfqyS1rDFjpump",
 "PASS2(EYo9,dev~0,sniped1.2)":"EYo9mCUK72tqTGS7TGyzCBjG6zVrXLS2GbUaY8EfqHGF",
 "REJECT(HNwc,rug,4tx,22s)":"HNwcHVQeV9MqbR9KhEWZK62Mfv48awKh4RCtxmMbpump",
}
def feats(mint):
    # page oldest-first full sig list
    alls=[]; before=None
    while True:
        b=sigs(mint,1000,before=before)
        if not b: break
        alls+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
        if len(alls)>8000: break
    alls=alls[::-1]  # oldest first
    if not alls: return None
    cslot=alls[0]["slot"]
    newest=alls[-1]["slot"]
    tspan=(alls[-1].get("blockTime") or 0)-(alls[0].get("blockTime") or 0)
    # create tx
    t0=tx(alls[0]["signature"]); time.sleep(0.1)
    creator=None; dev_buy=None; vanilla=1; flags={}
    insts0=[]
    if t0:
        msg=t0["transaction"]["message"]; meta=t0["meta"]
        keys=[k["pubkey"] for k in msg["accountKeys"]]
        creator=keys[0]
        dev_buy=-(meta["postBalances"][0]-meta["preBalances"][0])/1e9  # SOL spent by creator
        logs=meta.get("logMessages",[])
        insts0=[l.split("Instruction: ")[1] for l in logs if "Instruction: " in l]
        low="\n".join(logs).lower()
        for kw in ["mayhem","holder","reward","creator fee","cashback","fee_recipient","feebps"]:
            if kw in low: flags[kw]=True
        # vanilla heuristic: plain Create/CreateV2 + Buy, no mayhem/reward/fee keywords
        vanilla=0 if any(k in low for k in ["mayhem","holder","reward","cashback"]) else 1
    # count trades in first slots: fetch txs within cslot..cslot+3
    early=[s for s in alls if s["slot"]<=cslot+3]
    n_slot0=0; n_0_3=0; signers_slot0=set()
    # bound: at most first 40 early txs
    for s in early[:40]:
        tt=tx(s["signature"]); time.sleep(0.05)
        if not tt: 
            # still count by slot
            if s["slot"]==cslot: n_slot0+=1
            n_0_3+=1
            continue
        insts=[l.split("Instruction: ")[1] for l in tt["meta"].get("logMessages",[]) if "Instruction: " in l]
        isbuy=any("Buy" in x for x in insts); issell=any("Sell" in x for x in insts); iscreate=any("Create" in x for x in insts)
        sgnr=tt["transaction"]["message"]["accountKeys"][0]["pubkey"]
        if s["slot"]==cslot:
            n_slot0+=1
            if sgnr!=creator and (isbuy or issell): signers_slot0.add(sgnr)
        if s["slot"]<=cslot+3:
            n_0_3+=1
    # n_0_3 counts total txs in first 4 slots (create included). Subtract create to match "trades".
    return dict(mint=mint,total_tx=len(alls),create_slot=cslot,span_slots=newest-cslot,span_sec=tspan,
                creator=creator,dev_buy=round(dev_buy,4) if dev_buy is not None else None,
                vanilla=vanilla,flags=list(flags.keys()),create_insts=insts0,
                n_trades_slot0=max(0,n_slot0-1),cosnipers_slot0=len(signers_slot0),
                n_trades_0_3=max(0,n_0_3-1))
out={}
for lbl,m in TOKS.items():
    print("fetching",lbl,"...")
    f=feats(m); out[lbl]=f
    print(json.dumps(f,indent=1))
    print()
json.dump(out,open("/root/tmp_filter2/val_feats.json","w"),indent=1)

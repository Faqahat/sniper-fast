import json, sys
sys.path.insert(0,"/root/fill")
import scan
VSOL0=scan.VSOL0

OUR="FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
LIVE=[  # (create_slot, mint, dev_buy, our_sig)
 (458184187,"Ahf3LJfnwnfECBdMgibVcmatEr7Brep7KpQ4hKtzpump",1000000000,"4kcUgB61FYHJ2hN5TxXKCAMni7jHhekNYpH29YgkQsjN8L52Kad2tSLpgPJTiHn1w9tK4sWwb66jtkRhAer9EfbN"),
 (458185209,"5fg379An6FXQaxLKtgQ2zUH5cJsRV9pA2FwvFMxdpump",3200000000,"3K3YuCDxrUcgdsUJPTrSLz3zmWRtF2ppefbMYDtWPJgj9xuiHZG7cC91jB1n1c6cWCwputFs6P1TAcZVi9wggMLc"),
 (458187027,"JAWCk2KADnJHEXduQGtvvbvgjmBWFUr3bJscut9pump",3000000000,"22SnHYp73Pej98oPQLsY3chQLMKfbxD2evcLdqxxbSjL3TrF7XvxLTNwDjVKPzEEyQvuNp6n3h5LoDv3W3RrY7FZ"),
 (458187347,"7mfAPTpiu2LvTVMYEuGTUW6i5UtQLpypHqaADSMncbHZ",4400000000,"3B7R6vA1zaTWeYFFnHxGyhgxX2ycNvSDEF5kphZByhDmhBVWnTeTnUCAVXGpwfash5WQZTGrytXdus87AGP8v3zb"),
]

# richer 0slot/astralane/bloxroute sets+prefixes
ZEROSLOT={"Eb2KpSC8uMt9GmzyAEm5Eb1AAAgTjRaXWFjKaFj22Hh","6fQaVhYZA4w3MBSXjJ81Vf6W1EDYeUPXpgVQ6UQyE1Hy","4HiwLEP2Bzqmzx6gP3W6nkGFbefWtHf8Fj5YtdLHu4Xb","7toBU3inhmrARGngC7z6SjmdDmC23N8HHtdSUnShxLog","8mR3wB1nh4D6J9RUCugxUpc6ya8w38LPxZ3i5o6PzTJT","TpdxgNJBWZRL8UXF5mrEsyWxDWx9HQexA9P1eTWQ42p","D8f3WkQu6dCF3sRFWfd8SuJqP5EbJT8TfJ1X7Kq8vS"}
BLOX={"HWEoBxYs7ssKuudEjzjmpfJVX7Dvi7wescFsVx2L5yoY","3UQUKjhMKaY2S6bjcQD6yHB7utcZt5bfarRCmctpRtUd","FjmZZrFvhnqqb9ThCuMVnENaM3JGVuGWNyCAxRJcFpg9","HzYfeM7NnaHiZQPz7YkdbCHkwJqfjBbHZSQHDbqxVpa5","95cfoy472fcQHaw4tPGBTKpn6ZQnfEPfBgDQx6gcRmRg"}

def classify(dests):
    if not dests: return "direct/no-tip"
    labs=[]
    for d in dests:
        if d in scan.JITO: labs.append("jito")
        elif d in scan.HELIUS: labs.append("helius")
        elif d in BLOX: labs.append("bloxroute")
        elif d in ZEROSLOT: labs.append("0slot")
        elif d.startswith("noz") or d.startswith("TEMPa"): labs.append("nozomi")
        elif d.lower().startswith("astra") or d.startswith("AStR") or d.startswith("ASt"): labs.append("astralane")
        elif d.startswith("moon"): labs.append("moonbot")
        elif d.startswith("rapid"): labs.append("rapid")
        else: labs.append("other:"+d[:6])
    # priority
    for p in ["jito","helius","nozomi","astralane","0slot","bloxroute","moonbot","rapid"]:
        if p in labs: return p
    return labs[0]

def getbuys(mint,cslot):
    rows=[]
    for sd in (0,1):
        slot=cslot+sd
        blk=scan.getblock(slot)
        if not blk: continue
        for pos,tx in enumerate(blk["transactions"]):
            if not tx.get("meta") or tx["meta"].get("err"): continue
            keys=scan.keys_of(tx)
            if mint not in keys or scan.PUMP not in keys: continue
            logs=tx["meta"].get("logMessages") or []
            if not any("Instruction: Buy" in l for l in logs): continue
            e=scan.buy_event(tx)
            if not e: continue
            fp=keys[0]; cu_price,cu_limit=scan.compute_budget(tx)
            tp=scan.tips(tx,fp)
            sig=tx["transaction"]["signatures"][0]
            rows.append(dict(sig=sig,fp=fp,slot=slot,sd=sd,pos=pos,sol_in=e["sol"],tok_out=e["tok"],
                vsol=e["vsol"],vtok=e["vtok"],cu_price=cu_price,cu_limit=cu_limit,
                tip_lam=sum(t[1] for t in tp),dests=[t[0] for t in tp]))
    rows.sort(key=lambda r:(r["slot"],r["pos"]))
    # post-dev floor
    if rows and rows[0]["sol_in"] and (rows[0]["vsol"]-rows[0]["sol_in"])<=VSOL0*1.02:
        dev=rows[0]; floor=dev["vsol"]/dev["vtok"]; group=rows[1:]; devrow=dev
    else:
        f0=rows[0]; floor=(f0["vsol"]-f0["sol_in"])/(f0["vtok"]+f0["tok_out"]); group=rows; devrow=None
    sa=0
    for i,r in enumerate(group):
        r["floor"]=floor; r["fill"]=(r["sol_in"]/r["tok_out"])/floor; r["rank"]=i; r["sa"]=sa; sa+=r["sol_in"]
        r["sender"]=classify(r["dests"])
    return group,devrow,floor

front_senders=[]
for cslot,mint,devbuy,oursig in LIVE:
    group,dev,floor=getbuys(mint,cslot)
    ours=[r for r in group if r["fp"]==OUR or r["sig"]==oursig]
    ourrank=ours[0]["rank"] if ours else None
    print("="*90)
    print("MINT %s  create_slot=%d  dev_buy=%.2f SOL  co-snipers=%d  OUR_rank=%s"%(mint[:12],cslot,devbuy/1e9,len(group),ourrank))
    if dev: print("  dev(rank -1): sol=%.3f pos=%d sender=%s"%(dev["sol_in"]/1e9,dev["pos"],classify(dev["dests"])))
    print("  %-4s %-6s %-9s %-9s %-11s %-9s %-7s %s"%("rank","slot+","fill","sol_in","cu_price","tip_SOL","pos","sender [dests]"))
    for r in group:
        mark=" <== US" if (r["fp"]==OUR or r["sig"]==oursig) else ""
        if r["rank"]<=5 or mark:
            print("  %-4d sd%-4d %-9.3f %-9.4f %-11s %-9.5f %-7d %s%s"%(
                r["rank"],r["sd"],r["fill"],r["sol_in"]/1e9,str(r["cu_price"]),r["tip_lam"]/1e9,r["pos"],
                r["sender"]+" "+(",".join(d[:8] for d in r["dests"]) if r["dests"] else ""),mark))
    # collect rank0/rank1 front-runners that are AHEAD of us
    for r in group:
        if ourrank is None or r["rank"]<ourrank:
            if r["rank"]<=1:
                front_senders.append((mint,r["rank"],r["sender"],r["cu_price"],r["tip_lam"],r["fill"]))

print("\n"+"="*90)
print("RANK-0/RANK-1 FRONT-RUNNERS AHEAD OF US (across our %d live tokens):"%len(LIVE))
from collections import Counter
print("  sender tally:",Counter(f[2] for f in front_senders))
for f in front_senders:
    print("   mint %s rank%d sender=%-12s cu_price=%s tip=%.5f fill=%.3f"%(f[0][:10],f[1],f[2],str(f[3]),f[4]/1e9,f[5]))
